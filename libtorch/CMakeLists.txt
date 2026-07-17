cmake_minimum_required(VERSION 3.20)
project(kdm6ad_libtorch CXX)

# ── [C2] C++17 ──────────────────────────────────────────────────────────────
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ── strict IEEE FP (no FMA contraction) ─────────────────────────────────────
# The Fortran mp modules compile with -ffp-contract=off (configure.wrf
# per-file rules); mirror it here so scalar host-side math (fconst staging,
# test reference expressions) is two-rounding IEEE as well. Tensor-op kernels
# live inside libtorch and are unaffected either way.
add_compile_options(-ffp-contract=off)

# ── [C1] libtorch ───────────────────────────────────────────────────────────
# 사용자가 -DCMAKE_PREFIX_PATH=<libtorch root>로 지정. Python venv에 있는 libtorch를
# 쓰려면 venv의 torch/share/cmake/Torch가 PREFIX_PATH에 잡혀야 함.
find_package(Torch REQUIRED)
message(STATUS "Found Torch: ${TORCH_LIBRARIES}")
message(STATUS "Torch include: ${TORCH_INCLUDE_DIRS}")

# ── core library: kdm6 ──────────────────────────────────────────────────────
add_library(kdm6 STATIC
    src/ops.cpp
    src/slope.cpp
    src/progb.cpp
    src/warm.cpp
    src/satadj.cpp
    src/cold.cpp
    src/melt_freeze.cpp
    src/sedimentation.cpp
    src/sedimentation_conservative.cpp
    src/thermo.cpp
    src/state.cpp
    src/runtime.cpp
    src/coordinator.cpp
    src/cloud_dsd.cpp
)
target_include_directories(kdm6
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
)
target_link_libraries(kdm6 PUBLIC ${TORCH_LIBRARIES})
target_compile_options(kdm6 PRIVATE -Wall -Wextra -Wpedantic)
# kdm6_c shared lib에서 링크하려면 PIC 필요
set_target_properties(kdm6 PROPERTIES POSITION_INDEPENDENT_CODE ON)
# PR3 (docs/PR3_VISIBILITY_DESIGN.md §4.3): hide the core's symbols at COMPILE
# time. This STATIC target is absorbed into libkdm6_c; a static target's objects
# carry ITS visibility preset, so without this its ~166 kdm6:: symbols would be
# re-exported by the dylib. Hidden visibility governs the dynamic export table
# only — the test executables that link kdm6 statically still resolve every
# symbol (static linking is unaffected).
set_target_properties(kdm6 PROPERTIES
    CXX_VISIBILITY_PRESET     hidden
    VISIBILITY_INLINES_HIDDEN ON)

# ── ABI shared library: kdm6_c (Fortran 호출용) ─────────────────────────────
add_library(kdm6_c SHARED
    bridge/kdm6_c_api.cpp
)
target_include_directories(kdm6_c
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/bridge>
        $<INSTALL_INTERFACE:include>
)
target_link_libraries(kdm6_c PUBLIC kdm6)

# ── PR3: symbol visibility / export allowlist (docs/PR3_VISIBILITY_DESIGN.md) ─
# The shipped dylib must export ONLY the 9 C ABI functions (kdm6_c_api.h), not
# its ~1342-symbol internal world (kdm6::/libtorch/std). Two layers:
#  (1) compiler visibility hidden on BOTH this bridge and the static kdm6 core
#      above — each of the 9 is opted back in via KDM6_C_API in the header;
#  (2) a linker export allowlist as the load-bearing backstop (macOS
#      exported_symbols_list / Linux --version-script), which the symbol-surface
#      CI gate measures. KDM6_C_BUILD makes KDM6_C_API take the producer branch
#      on Windows (no effect on the macOS/Linux verification targets).
set_target_properties(kdm6_c PROPERTIES
    C_VISIBILITY_PRESET       hidden
    CXX_VISIBILITY_PRESET     hidden
    VISIBILITY_INLINES_HIDDEN ON)
target_compile_definitions(kdm6_c PRIVATE KDM6_C_BUILD=1)

if(APPLE)
    set(_kdm6_c_exports "${CMAKE_CURRENT_SOURCE_DIR}/bridge/kdm6_c.exports")
    target_link_options(kdm6_c PRIVATE "-Wl,-exported_symbols_list,${_kdm6_c_exports}")
    set_target_properties(kdm6_c PROPERTIES LINK_DEPENDS "${_kdm6_c_exports}")
elseif(UNIX)
    set(_kdm6_c_version_script "${CMAKE_CURRENT_SOURCE_DIR}/bridge/kdm6_c.map")
    target_link_options(kdm6_c PRIVATE "-Wl,--version-script,${_kdm6_c_version_script}")
    set_target_properties(kdm6_c PROPERTIES LINK_DEPENDS "${_kdm6_c_version_script}")
endif()

# ── PR3-B: versioned library (docs/PR3_VISIBILITY_DESIGN.md §5) ──────────────
# SOVERSION sets the ELF SONAME (libkdm6_c.so.2) / macOS compatibility version;
# VERSION sets the on-disk file version + the symlink chain. Major 2 ==
# KDM6_ABI_VERSION (kdm6_get_abi_version_c()), so the soname and the runtime ABI
# agree. This is packaging only — export table / install-name, no numerics.
set_target_properties(kdm6_c PROPERTIES
    VERSION   2.0.0
    SOVERSION 2)

# ── PR1-A: test-only fault-injection hooks (OFF for shipped builds) ──────────
# The thread-fence fail-closed path is exercised from the pure-C ABI test via
# an env seam; that seam must NEVER be present in the operational dylib (a
# shipped binary honoring a test env var is a foot-gun). Gated OFF by default;
# CI/dev enable -DKDM6_ENABLE_TEST_HOOKS=ON only to run the fail-path test.
option(KDM6_ENABLE_TEST_HOOKS
    "Compile test-only fault-injection hooks into kdm6_c (never for shipped builds)" OFF)
if(KDM6_ENABLE_TEST_HOOKS)
    # PRIVATE — never propagates to the kdm6 physics core or an installed header.
    target_compile_definitions(kdm6_c PRIVATE KDM6_ENABLE_TEST_HOOKS)
    message(WARNING "KDM6_ENABLE_TEST_HOOKS=ON: test-only ABI fault hooks are "
                    "compiled into kdm6_c — DEV/CI ONLY, never a shipped build.")
endif()

# ── tests ───────────────────────────────────────────────────────────────────
enable_testing()
add_executable(test_smoke tests/test_smoke.cpp)
target_link_libraries(test_smoke PRIVATE kdm6)
add_test(NAME smoke COMMAND test_smoke)
add_executable(test_slope tests/test_slope.cpp)
target_link_libraries(test_slope PRIVATE kdm6)
add_test(NAME slope COMMAND test_slope)
add_executable(test_progb tests/test_progb.cpp)
target_link_libraries(test_progb PRIVATE kdm6)
add_test(NAME progb COMMAND test_progb)
add_executable(test_warm tests/test_warm.cpp)
target_link_libraries(test_warm PRIVATE kdm6)
add_test(NAME warm COMMAND test_warm)
add_executable(test_satadj tests/test_satadj.cpp)
target_link_libraries(test_satadj PRIVATE kdm6)
add_test(NAME satadj COMMAND test_satadj)
# Operational-aux port verification (formerly the placeholder-gap regression).
# build_default_aux now computes n0r/n0i/n0c and work1_water/ice/r from the
# post-staging state (no static placeholders); this test asserts those
# production values + autograd-graph retention. See the test file header.
# (Target name kept for history; it is NOT a pending placeholder gap.)
add_executable(test_aux_placeholder_gap tests/test_aux_placeholder_gap.cpp)
target_link_libraries(test_aux_placeholder_gap PRIVATE kdm6)
add_test(NAME aux_placeholder_gap COMMAND test_aux_placeholder_gap)
add_executable(test_cold tests/test_cold.cpp)
target_link_libraries(test_cold PRIVATE kdm6)
add_test(NAME cold COMMAND test_cold)
add_executable(test_melt_freeze tests/test_melt_freeze.cpp)
target_link_libraries(test_melt_freeze PRIVATE kdm6)
add_test(NAME melt_freeze COMMAND test_melt_freeze)
add_executable(test_sedimentation tests/test_sedimentation.cpp)
target_link_libraries(test_sedimentation PRIVATE kdm6)
add_test(NAME sedimentation COMMAND test_sedimentation)
add_executable(test_thermo tests/test_thermo.cpp)
target_link_libraries(test_thermo PRIVATE kdm6)
add_test(NAME thermo COMMAND test_thermo)
add_executable(test_coordinator tests/test_coordinator.cpp)
target_link_libraries(test_coordinator PRIVATE kdm6)
add_test(NAME coordinator COMMAND test_coordinator)
add_executable(test_cloud_dsd tests/test_cloud_dsd.cpp)
target_link_libraries(test_cloud_dsd PRIVATE kdm6)
add_test(NAME cloud_dsd COMMAND test_cloud_dsd)
add_executable(test_c_abi tests/test_c_abi.cpp)
target_link_libraries(test_c_abi PRIVATE kdm6_c)
if(KDM6_ENABLE_TEST_HOOKS)
    target_compile_definitions(test_c_abi PRIVATE KDM6_ENABLE_TEST_HOOKS)
endif()
add_test(NAME c_abi COMMAND test_c_abi)
add_executable(test_autograd_endtoend tests/test_autograd_endtoend.cpp)
target_link_libraries(test_autograd_endtoend PRIVATE kdm6)
add_test(NAME autograd_endtoend COMMAND test_autograd_endtoend)
add_executable(test_handle_vjp tests/test_handle_vjp.cpp)
target_link_libraries(test_handle_vjp PRIVATE kdm6)
add_test(NAME handle_vjp COMMAND test_handle_vjp)
# conservative-interface-v1 C3 certification gates. Links BOTH kdm6 (direct
# substep + internal fp64/AD gates) and kdm6_c (public v2 f32 + kdm6_step_ad_c
# pin) — the dylib exports only the 9 C symbols, so no kdm6:: duplication.
# legacy_signature_caller.cpp is a SEPARATE TU calling the pre-PR22 signatures
# (kdm6_step 8-param / kdm6_fn 7-param): linking it proves the old mangled
# symbols still resolve, like a real already-compiled consumer (C3.6).
add_executable(test_conservative_interface
    tests/test_conservative_interface.cpp
    tests/legacy_signature_caller.cpp)
target_link_libraries(test_conservative_interface PRIVATE kdm6 kdm6_c)
add_test(NAME conservative_interface COMMAND test_conservative_interface)

# ── Fortran ISO_C_BINDING smoke (optional — Fortran 컴파일러 있을 때만) ──────
# KIM-meso 통합 시 `kdm6_iso_c` 모듈을 그대로 drop-in 사용. 컴파일러 없으면 skip.
include(CheckLanguage)
check_language(Fortran)
if(CMAKE_Fortran_COMPILER)
    enable_language(Fortran)
    add_executable(test_fortran_smoke
        bridge/kdm6_iso_c.f90
        tests/test_fortran_smoke.f90
    )
    target_link_libraries(test_fortran_smoke PRIVATE kdm6_c)
    add_test(NAME fortran_smoke COMMAND test_fortran_smoke)
    message(STATUS "Fortran enabled — test_fortran_smoke will be built")
else()
    message(STATUS "Fortran compiler not found — skipping test_fortran_smoke")
endif()

# ── keep asserts live in the test executables ────────────────────────────────
# The C++ tests validate via <cassert>. Under a Release build (-DNDEBUG) assert()
# expands to nothing, which would (a) leave every assert-based test hollow — it runs
# but verifies nothing — and (b) let a dangling member reference inside an assert
# compile silently (we hit exactly this: a removed-field ref survived a Release build).
# Force -UNDEBUG on the TEST targets only so their assertions actually execute in ctest.
# The kdm6 / kdm6_c libraries are intentionally left untouched, so the WRF-linked dylib
# stays -DNDEBUG-optimized.
foreach(t IN ITEMS
        test_smoke test_slope test_progb test_warm test_satadj test_aux_placeholder_gap
        test_cold test_melt_freeze test_sedimentation test_thermo test_coordinator
        test_cloud_dsd test_c_abi test_autograd_endtoend test_handle_vjp
        test_conservative_interface)
    if(TARGET ${t})
        target_compile_options(${t} PRIVATE -UNDEBUG)
    endif()
endforeach()

# ── installation ────────────────────────────────────────────────────────────
# NOTE: this is a plain file-copy install (libraries + headers), NOT a CMake
# package — there is no generated kdm6Config.cmake / exported target set, so
# `find_package(kdm6ad)` is intentionally unsupported. Consumers link the built
# libkdm6_c.dylib directly (see docs/HOST_INTEGRATION.md). We therefore omit the
# EXPORT clause rather than leave a half-configured `install(TARGETS … EXPORT)`
# with no matching `install(EXPORT …)`.
install(TARGETS kdm6 kdm6_c
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)
install(DIRECTORY include/ DESTINATION include)
install(FILES bridge/kdm6_c_api.h DESTINATION include/kdm6)
