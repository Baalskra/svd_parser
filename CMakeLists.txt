cmake_minimum_required(VERSION 3.15)

target_include_directories(${PROJECT_NAME} PUBLIC .)

file(GLOB_RECURSE sources *.h)

target_sources(${PROJECT_NAME} PUBLIC ${sources})