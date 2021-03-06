
import subprocess
import argparse
import os
from datetime import date
import time
import shutil
import stat
import sys
import json
import pprint

import MachineConfigs as machine_configs
import Helpers as helpers
import WriteTestResultsToHTML as write_test_results_to_html


class TestsSetError(Exception):
    pass

# Get the Executable Directory.
def get_executable_directory(configuration):
    if configuration.lower() == 'released3d12' or configuration.lower() == 'releasevk' :
        return "Bin\\x64\\Release\\"
    else:
        return "Bin\\x64\\Debug\\"


# Build the Solution.
def build_solution(relative_solution_filepath, configuration):

    try:
        # Build the Batch Args.
        batch_args = [machine_configs.machine_build_script, "rebuild", relative_solution_filepath, configuration.lower()]

        # Build Solution.
        if subprocess.call(batch_args) == 0:
            return 0

        else:
            raise TestsSetError("Error building solution : " + relative_solution_filepath + " with configuration : " + configuration.lower())

    except subprocess.CalledProcessError as subprocess_error:
        raise TestsSetError("Error building solution : " + relative_solution_filepath + " with configuration : " + configuration.lower())


def run_test_run(executable_filepath, current_arguments, output_file_base_name, output_directory):

    try:
        # Start the process and record the time.
        process = subprocess.Popen(executable_filepath  + ' ' + current_arguments + ' -outputfilename ' + output_file_base_name + ' -outputdir ' + output_directory)
        start_time = time.time()

        run_results = [True, ""]

        # Wait for the process to finish.
        while process.returncode is None:
            process.poll()
            current_time = time.time()

            difference_time = current_time - start_time

            # If the process has taken too long, kill it.
            if difference_time > machine_configs.machine_process_default_kill_time:
                print "Kill Process"
                process.kill()
                run_results = [False, "Process ran for too long, had to kill it. Please verify that the program finishes within its hang time, and that it does not crash"]
                break

        return run_results

    except (NameError, IOError, OSError) as e:
        print e.args
        raise TestsSetError('Error when trying to run ' + executable_filepath + ' ' + current_arguments + ' ' + 'with outputfilename ' + output_file_base_name + ' and outputdir ' + output_directory)


# Run the tests set..
def run_tests_set(main_directory, nobuild, json_filepath, results_directory, reference_directory):

    tests_set_run_result = {}
    tests_set_run_result['Tests Set Error Status'] = False
    tests_set_run_result['Tests Set Error Message'] = ""

    # Whether all tests in this set have passed
    tests_set_run_result['Success'] = True

    json_data = None
    print json_filepath

    try:
        # Try and open the json file.
        with open(json_filepath) as jsonfile:

            # Try and parse the data from the json file.
            try:
                json_data = json.load(jsonfile)
                tests_set_run_result['Tests Set Filename'] = os.path.splitext(os.path.basename(json_filepath))[0]
                tests_set_run_result['Tests Set Directory'] = os.path.dirname(json_filepath)
                tests_set_run_result['Tests Groups'] = json_data['Tests Groups']
                tests_set_run_result['Solution Target'] = json_data['Solution Target']
                tests_set_run_result['Configuration Target'] = json_data['Configuration Target']
                tests_set_run_result['Tests Set Results Directory'] = results_directory + '\\' + tests_set_run_result['Tests Set Filename'] + '\\'
                tests_set_run_result['Tests Set Reference Directory'] = reference_directory + '\\' + tests_set_run_result['Tests Set Filename'] + '\\'

                # Build solution unless disabled by command line argument
                if not nobuild:
                    try:
                        # Try and Build the Solution.
                        build_solution(main_directory + tests_set_run_result['Solution Target'], tests_set_run_result['Configuration Target'])

                    except TestsSetError as tests_set_error:
                        tests_set_run_result['Tests Set Error Status'] = True
                        tests_set_run_result['Tests Set Error Message'] = tests_set_error.args
                        tests_set_run_result['Success'] = False
                        return tests_set_run_result

                # Absolute path.
                absolutepath = os.path.abspath(os.path.dirname(main_directory))

                #
                for current_tests_group_name in tests_set_run_result['Tests Groups']:
                    current_tests_group = tests_set_run_result['Tests Groups'][current_tests_group_name]

                    current_tests_group['Results'] = {}
                    current_tests_group['Results']['Group Error Status'] = False
                    current_tests_group['Results']['Group Error Message'] = ""
                    current_tests_group['Results']['Results Error Status'] = {}
                    current_tests_group['Results']['Results Error Message'] = {}

                    # Get the executable directory.
                    executable_directory = absolutepath + '\\' + get_executable_directory(tests_set_run_result['Configuration Target'])
                    # Get the results directory.
                    current_results_directory = tests_set_run_result['Tests Set Results Directory'] + '\\' + current_tests_group_name + '\\'

                    # Create the directory, or clean it.
                    if helpers.directory_clean_or_make(current_results_directory) is None:
                        current_tests_group['Results']['Group Error Status'] = True
                        current_tests_group['Results']['Group Error Message'] = "Could not clean or make required results directory. Please try manually deleteing : " + current_results_directory

                    #   Check if the test is enabled.
                    if current_tests_group['Enabled'] == True:

                        # Initialize all the results.
                        current_tests_group['Results']["Run Results"] = {}
                        current_tests_group['Results']['Results Directory'] = current_results_directory
                        current_tests_group['Results']['Results Expected Filename'] = {}

                        # Run each test.
                        for index, current_test_args in enumerate(current_tests_group['Project Tests Args']) :

                            # Initialize the error status.
                            current_tests_group['Results']['Results Error Status'][index] = False
                            current_tests_group['Results']['Results Error Message'][index] = False

                            # Initialize the expected filename
                            current_tests_group['Results']['Results Expected Filename'][index] = current_tests_group_name + str(index) + '.json'

                            # Try running the test.
                            try:

                                executable_file = executable_directory + current_tests_group['Project Name'] + '.exe'
                                current_test_run_result = run_test_run(executable_file, current_test_args, current_tests_group_name + str(index), current_results_directory)
                                current_tests_group['Results']["Run Results"][index] = current_test_run_result

                                # Update overall test set success based on whether there was an error running it.
                                # Updating based on pass/fail checks happen later in analyze_tests_group()
                                tests_set_run_result['Success'] &= current_test_run_result[0]

                                if current_test_run_result[0] != True :
                                    current_tests_group['Results']['Results Error Status'][index] = True
                                    current_tests_group['Results']['Results Error Message'][index] = current_test_run_result[1]

                            # Check if an error occurred.
                            except (TestsSetError, IOError, OSError) as tests_set_error:
                                current_tests_group['Results']['Results Error Status'][index] = True
                                current_tests_group['Results']['Results Error Status'][index] = tests_set_error.args
                                tests_set_run_result['Success'] = False


                return tests_set_run_result

            # Exception Handling.
            except ValueError as e:
                tests_set_run_result['Tests Set Error Status'] = True
                tests_set_run_result['Tests Set Error Message'] = e.args
                tests_set_run_result['Success'] = False
                return tests_set_run_result


    # Exception Handling.
    except (IOError, OSError) as e:
        tests_set_run_result['Tests Set Error Status'] = True
        tests_set_run_result['Tests Set Error Message'] = e.args
        return tests_set_run_result


def verify_tests_groups_expected_output(test_groups):

    for current_tests_group_name in test_groups:
        if test_groups[current_tests_group_name]['Enabled'] == False:
            continue

        # For each of the runs, check the errors.
        for index, current_project_run in enumerate(test_groups[current_tests_group_name]['Project Tests Args']):
            expected_output_file = test_groups[current_tests_group_name]['Results']['Results Directory'] + current_tests_group_name + str(index) + '.json'

            #   Check if the expected file was created.
            if not os.path.isfile(expected_output_file) :
                test_groups[current_tests_group_name]['Results']['Results Error Status'][index] = True
                test_groups[current_tests_group_name]['Results']['Results Error Message'][index] = 'Could not find the expected json output file : ' + expected_output_file + ' . Please verify that the program ran correctly.'
                continue


#   Check the Tests Set Results, and create the output.
def get_tests_set_results(tests_set_run_results):

    # Check which ones managed to generate an output.
    tests_groups = tests_set_run_results['Tests Groups']
    verify_tests_groups_expected_output(tests_groups)

    # Check the json results for each one that is enabled.
    for current_tests_group_name in tests_groups:
        if tests_groups[current_tests_group_name]['Enabled'] == True:
            analyze_tests_group(tests_set_run_results, current_tests_group_name)


#   Check the json results for a single test.
def analyze_tests_group(tests_set_run_results, current_test_group_name):

    current_test_group = tests_set_run_results['Tests Groups'][current_test_group_name]
    current_test_group['Results']['Performance Checks'] = []
    current_test_group['Results']['Memory Checks'] = []
    current_test_group['Results']['Screen Capture Checks'] = []

    for index, current_test_args in enumerate(current_test_group['Project Tests Args']):
        if current_test_group['Results']['Results Error Status'][index] != True:

            # Try and parse the data from the json file.
            try:

                current_test_reference_directory = tests_set_run_results['Tests Set Reference Directory'] + '\\'  + '\\' + current_test_group_name + '\\'
                current_test_result_directory = current_test_group['Results']['Results Directory']
                result_json_filepath = current_test_result_directory + current_test_group['Results']['Results Expected Filename'][index]

                # Try and open the json file.
                with open(result_json_filepath) as result_json_file:

                    result_json_data = json.load(result_json_file)

                    # Analyze the screen captures. Assume Screen Capture test if no config specified
                    if 'Test Config' not in current_test_group or current_test_group['Test Config']['Type'] == "Image Compare":
                        tolerance = 0.0
                        if 'Test Config' in current_test_group and 'Tolerance' in current_test_group['Test Config']:
                            tolerance = current_test_group['Test Config']['Tolerance']

                        screen_capture_checks = analyze_screen_captures(tolerance, result_json_data, current_test_result_directory, current_test_reference_directory)
                        current_test_group['Results']['Screen Capture Checks'].append(screen_capture_checks)
                        tests_set_run_results['Success'] &= screen_capture_checks['Success']

                    # # Analyze the performance checks.
                    # if current_test_group['Test Config']['Type'] == "Performance Test":
                    #     performance_checks = analyze_performance_checks(result_json_data)
                    #     current_test_group['Results']['Performance Checks'][index] = performance_checks
                    #     # When check implemented, update success

                    # # Analyze the memory checks.
                    # if current_test_group['Test Config']['Type'] == "Memory Test":
                    #     memory_checks = analyze_memory_checks(result_json_data)
                    #     current_test_group['Results']['Memory Checks'][index] = memory_checks
                    #     # When check implemented, update success

            # Exception Handling.
            except (IOError, OSError, ValueError) as e:
                current_test_group['Results']['Results Error Status'][index] = True
                current_test_group['Results']['Results Error Message'][index] = 'Could not open the expected json output file : ' + result_json_filepath + ' . Please verify that the program ran correctly.'


#   Analyze the Performance Checks.
def analyze_performance_checks(result_json_data):
    return []

#   Analyze the Memory Checks.
def analyze_memory_checks(result_json_data):
    return []

def analyze_screen_captures(tolerance, result_json_data, current_test_result_directory, current_test_reference_directory):

    screen_captures_results = {}
    screen_captures_results['Success'] = True
    capture_data_keys = ['Frame Screen Captures', 'Time Screen Captures']

    for key in capture_data_keys:
        screen_captures_results[key] = []
        
        for index, frame_screen_captures in enumerate(result_json_data[key]):

            # Get the test result image.
            test_result_image_filename = current_test_result_directory + frame_screen_captures['Filename']

            # Get the reference image.
            test_reference_image_filename = current_test_reference_directory + frame_screen_captures['Filename']

            # Create the test compare image.
            test_compare_image_filepath = current_test_result_directory + os.path.splitext(frame_screen_captures['Filename'])[0] + '_Compare.png'

            # Run ImageMagick
            image_compare_command = ['magick', 'compare', '-metric', 'MSE', '-compose', 'Src', '-highlight-color', 'White', '-lowlight-color', 'Black', test_result_image_filename, test_reference_image_filename, test_compare_image_filepath]
            image_compare_process = subprocess.Popen(image_compare_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
            image_compare_result = image_compare_process.communicate()[0]

            # Keep the Return Code and the Result.
            result = {}

            # Image compare succeeded
            if image_compare_process.returncode <= 1: # 0: Success, 1: Does not match, 2: File not found, or other error?
                result_str = image_compare_result[:image_compare_result.find(' ')]
                result["Compare Result"] = result_str
                result["Test Passed"] = float(result_str) <= tolerance
            # Error
            else:
                result["Compare Result"] = "Error"
                result["Test Passed"] = False

            result["Return Code"] = image_compare_process.returncode
            result["Source Filename"] = test_result_image_filename
            result["Reference Filename"] = test_reference_image_filename

            screen_captures_results['Success'] &= result["Test Passed"]
            screen_captures_results[key].append(result)

    return screen_captures_results


def main():

    # Argument Parser.
    parser = argparse.ArgumentParser()

    # Add the Argument for which solution.
    parser.add_argument('-md', '--main_directory', action='store', help='Specify the path to the top level directory of Falcor. The path in the Tests Set file is assumed to be relative to that.')

    # Add the Argument for which configuration.
    parser.add_argument('-nb', '--no_build', action='store_true', help='Specify whether or not to build the solution.')

    # Add the Argument for which Tests Set to run.
    parser.add_argument('-ts', '--tests_set', action='store', help='Specify the Tests Set file.')

    # Parse the Arguments.
    args = parser.parse_args()

    # Get the machine constants.
    main_results_directory = machine_configs.machine_relative_checkin_local_results_directory
    main_reference_directory = machine_configs.machine_default_checkin_reference_directory

    #   Run the Test Set.
    tests_set_results = run_tests_set(args.main_directory, args.no_build, args.tests_set, main_results_directory, main_reference_directory)

    # Build the Tests Results.
    get_tests_set_results(tests_set_results)

    # Get the Tests Set HTML Result.
    if tests_set_results['Tests Set Error Status'] is True:
        html_file_content = write_test_results_to_html.writeErrorMessageHtml(tests_set_results['Tests Set Error Status'])
    else:
        # Write the Tests Results to HTML.
        html_file_content = write_test_results_to_html.write_test_set_results_to_html(tests_set_results)

    # Output the file to disk.

    # Build path and filename
    html_file_path = machine_configs.machine_relative_checkin_local_results_directory + '\\' + helpers.build_html_filename(tests_set_results)
    html_file = open(html_file_path, 'w')
    html_file.write(html_file_content)
    html_file.close()

    # Open it up.
    os.system("start " + html_file_path)


if __name__ == '__main__':
    main()
