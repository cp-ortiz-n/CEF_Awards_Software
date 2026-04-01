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
        self.verbose = True                 # Enables detailed prints (student scores, warnings, progress), False to mute most output

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


def process_high_school_application_scores(year: int, verbose: bool = False, DEBUG: bool = False, CALL_APIS: bool = False):
    """The main function that computes the high school student's scores and validates their application

    Parameters
    ----------
    file : str
        The file with all of the student's answers

    Returns
    -------

    """
    file = f'Student Answers for {str(year)} Incentive Awards.csv'
    with open(f'Student_Data/{file}', 'r', encoding="utf-8-sig") as csvinput:
        # get fieldnames from DictReader object and store in list
        d_reader = csv.DictReader(csvinput)
        headers = d_reader.fieldnames
        # Check if the questions exist in the file, most often a change in the year
        if not vali.questions_check(headers, year):
            return

        # Adding leading columns for the scores the students recieved
        headers = ['Total', 'GPA', 'ACTSAT', 'ACTMSATM', 'STEM', 'Reviewer', 'CommServ', 'Essay', 'Career', 'Bonus',
                   'Notes', 'home_to_school_dist', 'home_to_school_time_pt', 'home_to_school_time_car', 'ACT_value',
                   'ACTM_value'] + d_reader.fieldnames
        
        writer = csv.DictWriter(open(f'{year}_output.csv', 'w', newline='', encoding='utf-8-sig'), fieldnames=headers)

        writer.writeheader()
        # Load the conversions and lists into variables for reuse
        SAT_to_ACT_dict = util.conversion_dict('SAT_to_ACT.csv', 'int')
        SAT_to_ACT_Math_dict = util.conversion_dict('SAT_to_ACT_Math.csv', 'int')
        course_scores = util.conversion_dict('Course_scoring.csv', 'str')
        school_list, chicago_schools = vali.get_school_list('Illinois_Schools_Fix.csv')

        if year >= 2022:  # Only started getting this in 2022
            reviewer_feedback_df = util.get_review_feedback(f'{year} CEF Reviewer Detailed Feedback.xlsx')

        # Iterate through file once to get data for histograms
        ACT_Overall, ACTM_Overall = sutil.generate_histo_arrays(file, SAT_to_ACT_dict, SAT_to_ACT_Math_dict, year)

        if year in cs.normalizing_students:
            reviewer_scores = sutil.get_reviewer_scores_debiased(
                    f'Reviewer Scores by Applicant for {str(year)} Incentive Awards.csv', year)
        else:
            reviewer_scores = sutil.get_reviewer_scores(f'Reviewer Scores by Applicant for {year} Incentive Awards.csv')
        student_list = []
        cnt = 0
        for line in d_reader:
            cnt += 1
            # if cnt > 2:
            #    break
            lastName = line[cs.questions[year][0]['lastName']].strip()
            firstName = line[cs.questions[year][0]['firstName']].strip()

            # Debugging code, lets you skip to just the one you care about
            #firstName_override = ''
            #lastName_override = ''

            #if firstName != firstName_override and lastName != lastName_override:
            #    continue
            
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
            if (s.lastName == "Clemente"): 
                s.STEM_Classes = "Honors Physics, Honors Biology, Honors Chemistry, AP Computer Science, AP Environmental Science, Honors Integrated Math II, Honors Advanced Algebra with Trig, Honors Pre-Calculus, Dual Credit Calculus, Honors Principles of Engineering, Honors Civil Engineering and Architecture, Honors Digital Electronics, Honors Digital Imaging I, Honors Digital Imaging II"


            s.College = line[cs.questions[year][0]['College']]
            s.Other_College = line[cs.questions[year][0]['Other_College']]
            s.high_school_full = line[cs.questions[year][0]['high_school']]
            s.high_school_other = line[cs.questions[year][0]['high_school_other']]


            # s.student_type,
            print(s.firstName, s.lastName,  s.GPA_Value, s.ACT_SAT_value, s.ACTM_SATM_value,)

            if year >= 2021:
                s.submitted = line['Submit Application Complete']
            else:
                s.submitted = 'Yes'

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

            # A basic sanity check that if the GPA and ACT values are populated, then the applicant is probably applying
            if 1 == 1 and cs.high_schooler in s.student_type.upper() and s.GPA_Value and s.firstName != 'Test' and s.submitted == 'Yes':
                #print(s.lastName, s.firstName)
                # Validate the applicant's address is residential and that they live or go to high school in Chicago
                vali.address_validation(s, chicago_schools, school_list, verbose, DEBUG, CALL_APIS)

                # Validate the applicant is accepted into an ABET engineering program
                vali.accred_check(s, verbose, DEBUG)

                # Validate the applicants ACT/SAT scores and score their GPA and ACT/SAT
                sutil.GPA_Calc(s, True)
                sutil.ACT_SAT_Calc(s, SAT_to_ACT_dict, ACT_Overall, 'C', verbose, DEBUG)
                sutil.ACT_SAT_Calc(s, SAT_to_ACT_Math_dict, ACTM_Overall, 'M', verbose, DEBUG)

                # Score the applicant's verbose
                sutil.score_coursework(s, course_scores, True)

                # Determine the reviewer scores for the applicant
                if lastName.strip().upper() + firstName.strip().upper() in reviewer_scores:
                    s.reviewer_score = cs.reviewer_multiplier * round(
                            reviewer_scores[lastName.strip().upper() + firstName.strip().upper()])
                else:
                    s.reviewer_score = 0
                if year >= 2022:
                    try:
                        s.comm_score = round(
                                reviewer_feedback_df[reviewer_feedback_df['Applicant_'] == f'{lastName}, {firstName}'][
                                    'Community Service / Work_mean'].values[0], 2)
                        s.essay_score = round(
                                reviewer_feedback_df[reviewer_feedback_df['Applicant_'] == f'{lastName}, {firstName}'][
                                    'Short Essay_mean'].values[0], 2)
                        # s.career_score = round(                                reviewer_feedback_df[reviewer_feedback_df['Applicant_'] == f'{lastName}, {firstName}'][                                    'Career Goals_mean'].values[0], 2)
                        s.bonus_score = round(
                                reviewer_feedback_df[reviewer_feedback_df['Applicant_'] == f'{lastName}, {firstName}'][
                                    'Bonus/Discretionary Points_mean'].values[0], 2)
                        s.notes = \
                            reviewer_feedback_df[reviewer_feedback_df['Applicant_'] == f'{lastName}, {firstName}'][
                                'Notes_join'].values[0]
                    except Exception as e:
                        print(lastName, e)
                        s.comm_score = 0
                        s.essay_score = 0
                        s.career_score = 0
                        s.bonus_score = 0
                        s.notes = ''
                        print(f'{lastName}, {firstName} not found in reviewer feedback')
                if verbose:
                    print(
                        f'{lastName}, {firstName}: {s.GPA_Score} {s.ACT_SAT_Score} {s.ACTM_SATM_Score} {s.reviewer_score} {s.comm_score} {s.essay_score} {s.career_score} {s.bonus_score}')
                    pass


                # TODO: Send email with new students and warnings https://automatetheboringstuff.com/2e/chapter18/

                # Write back to output csv file
                total = s.GPA_Score + s.ACT_SAT_Score + s.ACTM_SATM_Score + s.reviewer_score + s.STEM_Score
                writer.writerow(dict(line,
                                     Total=total,
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
                                     ACTM_value=s.ACTM_value
                                     ))
                student_list.append(s)
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
    # TODO: VALIDATE THESE TWO TODOS: 
    # TODO: Remember to do the XGBoost on the missing ACTs
    # TODO: Iterate through the students here once and pass student class to the two functions

    year = 2025 # CHANGE THIS EVERY YEAR, also check the questions in constants.py to make sure they match the new file

    start = time.time()
    filename = f'Student Answers for {year} Incentive Awards.csv'

    # WARNING: Recheck the configurations before running the program, especially the CALL_APIS variable which will use your API credits if set to True
    (DEBUG, verbose, run_test_data, run_high_school_data, run_college_data, run_all_data, create_backup_copy, CALL_APIS) = Config()
    
    if run_test_data:
        run_validation_tests(verbose, DEBUG, CALL_APIS)

    if create_backup_copy:
        df = pd.read_csv(f'Student_Data/{filename}')
        backup_name = f'Modified_{datetime.now().strftime("%Y%m%d%H%M")}_{filename}'
        df.to_csv(f'Student_Data/copy_of_{backup_name}', index=False)

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
