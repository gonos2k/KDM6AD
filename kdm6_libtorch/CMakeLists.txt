cmake_minimum_required(VERSION 3.20)
project(kdm6_libtorch CXX)

# ── [C2] C++17 ──────────────────────────────────────────────────────────────
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

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
# Fortran-friendly: no name mangling, C linkage symbols visible
set_target_properties(kdm6_c PROPERTIES C_VISIBILITY_PRESET default)

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
add_test(NAME c_abi COMMAND test_c_abi)

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

# ── installation ────────────────────────────────────────────────────────────
install(TARGETS kdm6 kdm6_c
    EXPORT kdm6Targets
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
)
install(DIRECTORY include/ DESTINATION include)
install(FILES bridge/kdm6_c_api.h DESTINATION include/kdm6)
