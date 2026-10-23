if(NOT DEFINED PROGRAM OR NOT DEFINED WORK)
    message(FATAL_ERROR "PROGRAM and WORK are required")
endif()

file(REMOVE_RECURSE "${WORK}")
file(MAKE_DIRECTORY "${WORK}")
set(request "${WORK}/truncated.request")
set(result "${WORK}/should-not-exist.result")
file(WRITE "${request}" "K6BUDG1")

execute_process(
    COMMAND "${PROGRAM}" --input "${request}" --output "${result}"
    RESULT_VARIABLE status
    OUTPUT_VARIABLE stdout
    ERROR_VARIABLE stderr)
if(status EQUAL 0)
    message(FATAL_ERROR "truncated request unexpectedly succeeded: ${stdout} ${stderr}")
endif()
if(EXISTS "${result}")
    message(FATAL_ERROR "rejected request left a published result")
endif()
