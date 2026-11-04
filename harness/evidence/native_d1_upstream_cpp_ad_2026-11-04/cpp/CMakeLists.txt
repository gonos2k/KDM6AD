cmake_minimum_required(VERSION 3.20)
project(kdm6_native_d1_upstream_cpp_ad LANGUAGES CXX)

if(NOT DEFINED KDM6_CAPTURE_ROOT)
  message(FATAL_ERROR "KDM6_CAPTURE_ROOT must name the retained native D1 ProgB build")
endif()
find_package(Torch REQUIRED)

add_executable(native_d1_upstream_cpp_ad main.cpp)
target_include_directories(native_d1_upstream_cpp_ad PRIVATE
  "${KDM6_CAPTURE_ROOT}/source/include")
target_link_libraries(native_d1_upstream_cpp_ad PRIVATE
  "${KDM6_CAPTURE_ROOT}/build/libkdm6.a" ${TORCH_LIBRARIES})
target_compile_features(native_d1_upstream_cpp_ad PRIVATE cxx_std_17)
target_compile_options(native_d1_upstream_cpp_ad PRIVATE -ffp-contract=off -Wall -Wextra -Wpedantic)
target_compile_definitions(native_d1_upstream_cpp_ad PRIVATE KDM6_CAPTURE_VARIANT=1)

if(CMAKE_CXX_FLAGS MATCHES "(^| )-DNDEBUG( |$)" OR
   CMAKE_CXX_FLAGS_RELEASE MATCHES "(^| )-DNDEBUG( |$)")
  if(CMAKE_BUILD_TYPE STREQUAL "Release")
    message(FATAL_ERROR "This test executable requires assertions enabled; use an empty/Debug build type")
  endif()
endif()
