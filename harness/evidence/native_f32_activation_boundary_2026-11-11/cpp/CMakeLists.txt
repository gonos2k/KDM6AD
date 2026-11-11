cmake_minimum_required(VERSION 3.20)
project(native_f32_cabi_probe LANGUAGES CXX)

add_executable(native_f32_cabi_probe main.cpp)
target_compile_features(native_f32_cabi_probe PRIVATE cxx_std_17)
target_compile_options(native_f32_cabi_probe PRIVATE -ffp-contract=off -Wall -Wextra -Wpedantic)
target_include_directories(native_f32_cabi_probe PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../source/bridge")
if(APPLE)
  target_link_libraries(native_f32_cabi_probe PRIVATE ${CMAKE_DL_LIBS})
  target_link_options(native_f32_cabi_probe PRIVATE
    "-Wl,-rpath,/opt/homebrew/Caskroom/miniforge/base/lib/python3.9/site-packages/torch/lib")
endif()
if(CMAKE_BUILD_TYPE STREQUAL "Release" AND
   (CMAKE_CXX_FLAGS MATCHES "(^| )-DNDEBUG( |$)" OR
    CMAKE_CXX_FLAGS_RELEASE MATCHES "(^| )-DNDEBUG( |$)"))
  message(FATAL_ERROR "Evidence runner must keep assertions enabled")
endif()
