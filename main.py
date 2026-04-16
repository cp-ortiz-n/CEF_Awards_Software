"""
The main file for the project which runs by default validations for all high school and college applicants.
It also generates a score for each applicant based on predefined criteria.
"""

import csv
import time
import logging
import pandas as pd
import constants as cs

from datetime import datetime
from classes import Student
from utils import validations as vali, scoring_util as sutil, util, unittests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Config:
    """A class to hold all of the configuration variables for the program."""

    def __init__(self):
        # Logging / verbosity
        self.DEBUG = True                   # Enables debug-level behavior in functions (eg. stricter checks, more logs)
        self.verbose = False                 # Enables detailed prints (student scores, warnings, progress), False to mute most output

        # Active runtimes
        self.run_test_data = False          # Run test data + unit tests
        self.run_high_school_data = True    # Run high school student pipeline
        self.run_college_data = False       # Run college student pipeline
        self.run_all_data = False           # Run both high school and college pipelines on all data (overrides the two above)
        self.create_backup_copy = False     # Create timestamped backup of input CSV before processing

        # External calls
        self.CALL_APIS = False              # If True, calls Google and SmartyStreets API (uses credits)

    def __iter__(self):
        return iter([
            self.DEBUG,
            self.verbose,
            self.run_test_data,
            self.run_high_school_data,
            self.run_college_data,
            self.run_all_data,
            self.create_backup_copy,
            self.CALL_APIS,
        ])


def load_csv_and_validate_headers(year: int): 
    """Load the student answers CSV file and validate that the expected headers are present.

    Parameters
    ----------
    year : int
        The year of the application cycle, used to pull the correct questions from constants.py and to check for changes in the file format

    Returns
    -------
    csvinput : file object
        The opened CSV file object for the student answers
    dict_reader : csv.DictReader
        A DictReader object for iterating through the student answers
    headers : list
        A list of the headers in the CSV file
    """
    student_answers_file = f'Student Answers for {str(year)} Incentive Awards.csv'
    csvinput = open(f'processingDataFiles/{student_answers_file}', 'r', encoding="utf-8-sig")
    dict_reader = csv.DictReader(csvinput)
    headers = dict_reader.fieldnames
    
    if not vali.questions_check(headers, year):
        logger.error('CSV header validation failed for year %s. Please check the input file format and the questions in constants.py.', year)
        csvinput.close()
        return None, None, None
    
    return csvinput, dict_reader, headers


def setup_output_writer(year: int, headers: list): 
    """Set up the CSV DictWriter for the output file, including adding new headers for the scores.

    Parameters
    ----------
    year : int
        The year of the application cycle, used to name the output file
    headers : list
        The original headers from the input CSV file

    Returns
    -------
    writer : csv.DictWriter
        A DictWriter object for writing to the output CSV file with the new score headers included

    """
    output_file = f'outputs/{year}_output.csv'
    score_headers = ['Total', 'GPA', 'ACTSAT', 'ACTMSATM', 'STEM', 'Reviewer', 'CommServ', 'Essay', 'Career', 'Bonus',
                     'Notes', 'home_to_school_dist', 'home_to_school_time_pt', 'home_to_school_time_car', 'ACT_value',
                     'ACTM_value', 'Error_Messages']
    
    all_headers = score_headers + headers
    writer = csv.DictWriter(open(output_file, 'w', newline='', encoding='utf-8-sig'), fieldnames=all_headers)
    writer.writeheader()
    
    return writer


def load_reference_data(year: int):
    """Load all of the reference data files (conversion tables, school lists, reviewer scores) into variables for reuse.

    Parameters
    ----------
    year : int
        The year of the application cycle, used to pull the correct questions from constants.py and to check for changes in the file format

    Returns
    -------
    A tuple containing all of the reference data variables needed for processing and scoring the student applications, including:
    - SAT_to_ACT_dict: 
        A dictionary for converting SAT scores to ACT scores
    - SAT_to_ACT_Math_dict: 
        A dictionary for converting SAT Math scores to ACT Math
    - course_scores: 
        A dictionary for scoring the applicant's coursework based on their listed classes
    - school_list:
        A list of valid high schools for the award
    - chicago_schools:
        A list of high schools in Chicago for validating the applicant's connection to Chicago
    - reviewer_feedback_df:
        A DataFrame containing the detailed feedback from reviewers for each applicant (only available for 2022 and later)
    - reviewer_scores:
        A dictionary of the overall reviewer scores for each applicant
    - ACT_Overall:
        A list of ACT score distributions for the overall applicant pool, used for scoring
    - ACTM_Overall: 
        A list of ACT Math score distributions for the overall applicant pool, used for scoring
    """

    SAT_to_ACT_dict = util.conversion_dict('SAT_to_ACT.csv', 'int')
    SAT_to_ACT_Math_dict = util.conversion_dict('SAT_to_ACT_Math.csv', 'int')
    course_scores = util.conversion_dict('Course_scoring.csv', 'str')
    school_list, chicago_schools = vali.get_school_list('Illinois_Schools_Fix.csv')

    reviewer_feedback_df = util.get_review_feedback(f'processingDataFiles/{year} CEF Reviewer Detailed Feedback.xlsx')
    ACT_Overall, ACTM_Overall = sutil.generate_histo_arrays(f'Student Answers for {year} Incentive Awards.csv', SAT_to_ACT_dict, SAT_to_ACT_Math_dict, year)

    if year in cs.normalizing_students:
        reviewer_scores = sutil.get_reviewer_scores_debiased(f'Reviewer Scores by Applicant for {str(year)} Incentive Awards.csv', year)
    else:
        reviewer_scores = sutil.get_reviewer_scores(f'Reviewer Scores by Applicant for {year} Incentive Awards.csv')

    return {
        'SAT_to_ACT_dict': SAT_to_ACT_dict,
        'SAT_to_ACT_Math_dict': SAT_to_ACT_Math_dict,
        'course_scores': course_scores,
        'school_list': school_list,
        'chicago_schools': chicago_schools,
        'reviewer_feedback_df': reviewer_feedback_df,
        'reviewer_scores': reviewer_scores,
        'ACT_Overall': ACT_Overall,
        'ACTM_Overall': ACTM_Overall
    }


def create_student_instance(line: dict, year: int, CALL_APIS): 
    """
    Create and populate a student instance from a line of the input CSV file. 

    Parameters
    ----------
    line : dict
        A dictionary representing a row from the input CSV file
    year : int
        The year of the application cycle
    CALL_APIS : bool
        If True, calls external APIs for address validation and geocoding

    Returns
    -------
    s : Student
        A populated Student instance
    """
    lastName = line[cs.questions[year][0]['lastName']].strip()
    firstName = line[cs.questions[year][0]['firstName']].strip()
    s = Student.Student(firstName, lastName)

    s.GPA_Value = util.get_num(line[cs.questions[year][0]['GPA_Value']])
    s.ACT_SAT_value = util.get_num(line[cs.questions[year][0]['ACT_SAT_value']])
    s.ACTM_SATM_value = util.get_num(line[cs.questions[year][0]['ACTM_SATM_value']])

    s.COMMS_value = util.get_num(line[cs.questions[year][0]['COMMS_value']])
    s.NON_ENG_value = line[cs.questions[year][0]['NON_ENG_value']]
    s.student_type = line[cs.questions[year][0]['student_type']]

    s.major = line['Major']
    s.other_major = line[cs.questions[year][0]['other_major']]
    s.STEM_Classes = line[cs.questions[year][0]['STEM_Classes']]

    s.College = line[cs.questions[year][0]['College']]
    s.Other_College = line[cs.questions[year][0]['Other_College']]
    s.high_school_full = line[cs.questions[year][0]['high_school']]
    s.high_school_other = line[cs.questions[year][0]['high_school_other']]
    
    s.submitted = line['Submit Application Complete']

    s.address1 = line[cs.questions[year][0]['address1']]
    s.address2 = line[cs.questions[year][0]['address2']]
    s.city = line[cs.questions[year][0]['city']]
    s.state = line[cs.questions[year][0]['state']]
    s.zip_code = line[cs.questions[year][0]['zip']]

    if CALL_APIS is False:
        s.cleaned_address1 = line[cs.questions[year][0]['address1']]
        s.cleaned_address2 = line[cs.questions[year][0]['address2']]
        s.cleaned_city = line[cs.questions[year][0]['city']]
        if s.cleaned_city != 'Chicago' and s.firstName == 'ChicagoSchoolNoCHome':
            s.ChicagoHome = False
            s.validationError = True
        s.cleaned_state = line[cs.questions[year][0]['state']]
        s.cleaned_zip_code = line[cs.questions[year][0]['zip']]

    return s


def validate_high_school_student(s, ref_data, verbose, DEBUG, CALL_APIS):
    """
    Validate a high school student's application data based on the criteria for the award.

    Parameters
    ----------
    s : Student
        The Student instance to validate
    ref_data : tuple
        A tuple containing all of the reference data variables needed for validation
    year : int
        The year of the application cycle
    verbose : bool
        If True, prints detailed information about any warnings during validation
    DEBUG : bool
        If True, enables debug-level behavior in functions (eg. stricter checks, more logs)
    CALL_APIS : bool
        If True, calls external APIs for address validation and geocoding

    Returns
    -------
    bool
        True if the student passes all validation checks and should be scored, False if the student fails any validation checks and should not be scored
    """    
    SAT_to_ACT_dict = ref_data['SAT_to_ACT_dict']
    SAT_to_ACT_Math_dict = ref_data['SAT_to_ACT_Math_dict']
    course_scores = ref_data['course_scores']
    school_list = ref_data['school_list']
    chicago_schools = ref_data['chicago_schools']
    ACT_Overall = ref_data['ACT_Overall']
    ACTM_Overall = ref_data['ACTM_Overall']
    error_messages = []

    if (s.student_type.strip() == ''):
        error_messages.append('Student type is missing')

    if not (cs.high_schooler in s.student_type.upper()):
        return False  # Not a high school student, no need to run the rest of the checks

    if (not s.GPA_Value): 
        error_messages.append('GPA value is missing')
    
    if (not s.submitted == 'Yes'):
        error_messages.append('Application not marked as submitted')

    # Validate the applicant's address is residential and that they live or go to high school in Chicago
    vali.address_validation(s, chicago_schools, school_list, verbose, DEBUG, CALL_APIS)
    
    # Validate the applicant is accepted into an ABET engineering program
    vali.accred_check(s, verbose, DEBUG)

    sutil.GPA_Calc(s, verbose, DEBUG)
    sutil.ACT_SAT_Calc(s, SAT_to_ACT_dict, ACT_Overall, 'C', verbose, DEBUG)
    sutil.ACT_SAT_Calc(s, SAT_to_ACT_Math_dict, ACTM_Overall, 'M', verbose, DEBUG)

    # Score the applicant's coursework based on their listed classes and the course scoring rubric
    sutil.score_coursework(s, course_scores, verbose, DEBUG)

    if s.error_messages:
        if (not "UNRECOGNIZED" in s.error_messages[-1].upper()):
            return False

    return True

def process_and_score_high_school_student(s, ref_data, verbose, DEBUG, CALL_APIS):
    """
    Process and score a high school student based on their application data and the reference data.

    Parameters
    ----------
    s : Student
        The Student instance to process and score
    ref_data : tuple
        A tuple containing all of the reference data variables needed for processing and scoring
    year : int
        The year of the application cycle
    verbose : bool
        If True, prints detailed information about the student's scores and any warnings during processing
    DEBUG : bool
        If True, enables debug-level behavior in functions (eg. stricter checks, more logs)
    CALL_APIS : bool
        If True, calls external APIs for address validation and geocoding

    Returns
    -------
    s : Student
        The processed and scored Student instance with all relevant fields populated
    """
    
    validate_high_school_student(s, ref_data, verbose, DEBUG, CALL_APIS) 
    if not cs.high_schooler in s.student_type.upper():
        return False
        #if not validate_high_school_student(s, ref_data, verbose, DEBUG, CALL_APIS): 
        # if cs.high_schooler in s.student_type.upper():
        #    logger.warning('#################################################')
        #    logger.warning('Student %s, %s failed high school validation checks and will not be scored', s.lastName, s.firstName)
        #    validation_error_message = ' | '.join(s.error_messages)
        #    logger.warning('Student %s, %s failed the following checks: %s', s.lastName, s.firstName, validation_error_message)
        #    logger.warning('#################################################')
        # return False
    
    if s.unrecognized_courses:
        logger.warning('-------------------------------------------------')
        logger.warning('Student %s, %s has unrecognized courses that need validating: %s', s.lastName, s.firstName, s.unrecognized_courses)
        validation_error_message = ' | '.join(s.error_messages)
        logger.warning('Student %s, %s failed the following checks: %s', s.lastName, s.firstName, validation_error_message)
        logger.warning('-------------------------------------------------')

    reviewer_feedback_df = ref_data['reviewer_feedback_df']
    reviewer_scores = ref_data['reviewer_scores']
    
    review_scores_key = s.lastName.strip().upper() + s.firstName.strip().upper()
    if review_scores_key in reviewer_scores:
        s.reviewer_score = cs.reviewer_multiplier * round(reviewer_scores[review_scores_key])
    else: 
        s.reviewer_score = 0

    review_feedback_key = f'{s.lastName}, {s.firstName}'
    try:
        s.comm_score = round(
                reviewer_feedback_df[reviewer_feedback_df['Applicant_'] == review_feedback_key][
                    'Community Service / Work_mean'].values[0], 2)
        s.essay_score = round(
                reviewer_feedback_df[reviewer_feedback_df['Applicant_'] == review_feedback_key][
                    'Short Essay_mean'].values[0], 2)
        s.bonus_score = round(
                reviewer_feedback_df[reviewer_feedback_df['Applicant_'] == review_feedback_key][
                    'Bonus/Discretionary Points_mean'].values[0], 2)
        s.notes = \
            reviewer_feedback_df[reviewer_feedback_df['Applicant_'] == review_feedback_key][
                'Notes_join'].values[0]
    except Exception as _:
        s.comm_score = 0
        s.essay_score = 0
        s.career_score = 0
        s.bonus_score = 0
        s.notes = ''

        logger.warning(f'{s.lastName}, {s.firstName} not found in reviewer feedback')
    
    s.total_review_score = s.GPA_Score + s.ACT_SAT_Score + s.ACTM_SATM_Score + s.reviewer_score + s.STEM_Score

    logger.info('Processed student: %s, %s - Total Score: %s', s.lastName, s.firstName, s.total_review_score)
    return True

def process_high_school_application_scores(year: int, verbose: bool = False, DEBUG: bool = False, CALL_APIS: bool = False):
    csvinput, dict_reader, headers = load_csv_and_validate_headers(year)
    if dict_reader is None or headers is None:
        logger.error('Failed to load CSV or validate headers for year %s. Aborting high school processing.', year)
        return []
    
    try: 
        writer = setup_output_writer(year, headers)
        ref_data = load_reference_data(year)
        student_list = []
        unrecognized_courses = []

        for line in dict_reader:
            s = create_student_instance(line, year, CALL_APIS)
            if process_and_score_high_school_student(s, ref_data, verbose, DEBUG, CALL_APIS):
                if s.unrecognized_courses:
                    unrecognized_courses.extend(s.unrecognized_courses)
                writer.writerow(dict(line,
                                    Total=s.total_review_score,
                                    GPA=s.GPA_Score,
                                    ACTSAT=s.ACT_SAT_Score,
                                    ACTMSATM=s.ACTM_SATM_Score,
                                    STEM=s.STEM_Score,
                                    Reviewer=s.reviewer_score,
                                    CommServ=s.comm_score,
                                    Essay=s.essay_score,
                                    Career=s.career_score,
                                    Bonus=s.bonus_score,
                                    Notes=s.notes,
                                    home_to_school_dist=s.home_to_school_dist,
                                    home_to_school_time_pt=s.home_to_school_time_pt,
                                    home_to_school_time_car=s.home_to_school_time_car,
                                    ACT_value=s.ACT_value,
                                    ACTM_value=s.ACTM_value, 
                                    Error_Messages=' | '.join(s.error_messages)
                                    ))

                student_list.append(s)
    finally: 
        csvinput.close()

    logger.warning(f'Unrecognized courses across all students: {unrecognized_courses}')

    # student_names = list(set(f"{s.firstName.upper()} {s.lastName.upper()}" for s in student_list))
    # print(len(student_names), 'unique students processed:')

    return student_list


def process_college_application_scores(file: str, year: int, verbose: bool = False, DEBUG: bool = False, CALL_APIS: bool = False):
    """The main function that checks college student's eligibility for the award

    Parameters
    ----------
    file : str
        The file with all of the student's answers


    Returns
    -------

    """

    with open('Student_Data/' + str(file), 'r', encoding="utf-8-sig") as f:
        # get fieldnames from DictReader object and store in list
        d_reader = csv.DictReader(f)
        headers = d_reader.fieldnames

        # Check if the questions exist in the file, most often a change in the year
        if not vali.questions_check(headers, 2025):
            return

        recipient_list = vali.get_past_recipients('2019 Recipients.csv', 2019)
        college_students = []

        # print(headers)
        for line in d_reader:
            lastName = line[cs.questions['lastName']]
            firstName = line[cs.questions['firstName']]

            s = Student.Student(firstName, lastName)

            s.student_type = line[cs.questions['student_type']]
            s.GPA_Value = line[cs.questions['GPA_Value']]
            s.major_school_change = line[cs.questions['major_school_change']]
            s.major = line['Major']
            s.NON_ENG_value = line[cs.questions['NON_ENG_value']]

            if cs.college_student in s.student_type.upper():

                # Validate if the student is a past recipient, if not no point in other checks
                if vali.past_recipient(s, recipient_list, verbose, DEBUG):
                    # Validate GPA
                    vali.college_gpa(s, verbose, DEBUG)

                    # Validate that the recipient's college and major are still valid
                    vali.college_school_major(s, verbose, DEBUG)
                college_students.append(s)
    return college_students


def load_student_data(file: str, verbose: bool = False, DEBUG: bool = False) -> tuple[list, list]:
    """Run through the student file to generate a list of the students with their class variable set

    Parameters
    ----------
    file : str
        The file with all of the student's answers

    Returns
    -------
    high_school_students : list
        A list containing instances of the Student class of all the high school students
    college_students : list
        A list containing instances of the Student class of all the high school students

    """

    high_school_students = []
    college_students = []
    with open('Student_Data/' + str(file), 'r', encoding="utf-8-sig") as f:
        # get fieldnames from DictReader object and store in list
        d_reader = csv.DictReader(f)
        headers = d_reader.fieldnames

        # Check if the questions exist in the file, most often a change in the year
        if not vali.questions_check(headers):
            return high_school_students, college_students

    return high_school_students, college_students


def run_validation_tests(verbose, DEBUG, CALL_APIS):
    """Run validation tests on the test data files."""

    filename = 'Validation_Students.csv'
    student_data_time = time.time()
    validation_HS = process_high_school_application_scores(filename, verbose, DEBUG, CALL_APIS)
    HS_Run = time.time()
    logger.info('Runtime of HS Validation: %s', HS_Run - student_data_time)
    unittests.unit_tests(validation_HS, CALL_APIS)

    validation_C = process_college_application_scores(filename, 2025, verbose, DEBUG, CALL_APIS)
    logger.info('Runtime of College Validation: %s', time.time() - HS_Run)
    unittests.unit_tests(validation_C, CALL_APIS)


def run_stage(name: str, count_label: str = None, action = None):
    """Run a stage of the program with logging and timing.

    Parameters
    ----------
    name : str
        The name of the stage (for logging purposes)
    action : function
        The function to execute for this stage
    count_label : str
        The label to use when logging the count of items processed in this stage

    Returns
    -------
    result
        The result of the action function
    """
    start_time = time.time()
    result = action()
    elapsed_time = time.time() - start_time
    logger.info('Stage %s runtime: %.3f sec', name, elapsed_time)

    if result is None: 
        return result

    if isinstance(result, tuple):
        total = sum(len(r) for r in result if hasattr(r, '__len__'))
        logger.info('%s total students: %d', name, total)
    elif hasattr(result, '__len__'):
        logger.info('%s %s count: %d', name, count_label, len(result))

    return result


def main():
    """
    The main function which runs the program
    """

    year = 2026 # CHANGE THIS EVERY YEAR, also check the questions in constants.py to make sure they match the new file

    start = time.time()
    filename = f'Student Answers for {year} Incentive Awards.csv'

    # WARNING: Recheck the configurations before running the program, especially the CALL_APIS variable which will use your API credits if set to True
    (DEBUG, verbose, run_test_data, run_high_school_data, run_college_data, run_all_data, create_backup_copy, CALL_APIS) = Config()

    if run_test_data:
        run_validation_tests(verbose, DEBUG, CALL_APIS)

    if create_backup_copy:
        df = pd.read_csv(f'processingDataFields/{filename}')
        backup_name = f'Modified_{datetime.now().strftime("%Y%m%d%H%M")}_{filename}'
        df.to_csv(f'outputs/copy_of_{backup_name}', index=False)

    if run_all_data:
        _ = run_stage(
            name = 'All Data',
            count_label ='Students Count',
            action = lambda: load_student_data(filename, verbose, DEBUG)
        )

    if run_high_school_data:
        _ = run_stage(
            name = 'High School Scoring',
            count_label = 'Student Count',
            action = lambda: process_high_school_application_scores(year, verbose, DEBUG, CALL_APIS)
        )
    
    if run_college_data:
        _ = run_stage(
            name = 'College Scoring',
            count_label = 'Student Count',
            action = lambda: process_college_application_scores(filename, year, verbose, DEBUG, CALL_APIS)
        )

    logger.info('Runtime for total processing: %s seconds', time.time() - start)


if __name__ == '__main__':
    main()
