cmake_minimum_required(VERSION 3.15)

set(peripheral_library_name _peripherals)

file(GLOB_RECURSE peripheral_sources *.h)

#target_sources(${PROJECT_NAME} PUBLIC ${sources})

add_bsp_based_library(NAME ${peripheral_library_name} SOURCES ${peripheral_sources})
target_include_directories(${peripheral_library_name} PUBLIC .)
target_compile_options(${peripheral_library_name} PRIVATE -fdata-sections -ffunction-sections -O0)