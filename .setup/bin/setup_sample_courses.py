#!/usr/bin/env python3
"""
Setup script that reads in the users.yml and courses.yml files in the ../data directory and then
creates the users and courses for the system. This is primarily used by Vagrant and Travis to
figure the environments easily, but it could be run pretty much anywhere, unless the courses
already exist as else the system will probably fail.

Usage: ./setup_sample_courses.py
       ./setup_sample_courses.py [course [course]]
       ./setup_sample_courses.py --help

The first will create all courses in courses.yml while the second will only create the courses
specified (which is useful for something like Travis where we don't need the "demo classes", and
just the ones used for testing.)

Note about editing:
If you make changes that use/alter random number generation, you may need to 
edit the following files:
    Peer Review:
        students.txt
        graders.txt
    Office Hours Queue:
        queue_data.json
    Discussion Forum:
        threads.txt
        posts.txt
        
These files are manually written for a given set of users (the set is predetermined due to 
the random's seed staying the same). If you make any changes that affects the contents of the 
set these files will be outdated and result in failure of recreate_sample_courses.
"""
from __future__ import print_function, division
import argparse
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from shutil import copyfile
import glob
import grp
import hashlib
import json
import os
import pwd
import random
import shutil
import subprocess
import uuid
import os.path
import string
import pdb
import docker
import random
from sample_courses.sample_course_courses import Course 

from sample_courses.sample_course_gradeables import Gradeable  
from tempfile import TemporaryDirectory

from submitty_utils import dateutils

from sample_course_utils import *

from ruamel.yaml import YAML
from sqlalchemy import create_engine, Table, MetaData, bindparam, select, join, func

yaml = YAML(typ='safe')

CURRENT_PATH = os.path.dirname(os.path.realpath(__file__))
SETUP_DATA_PATH = os.path.join(CURRENT_PATH, "..", "data")

# Default values, will be overwritten in `main()` if corresponding arguments are supplied
SUBMITTY_INSTALL_DIR = "/usr/local/submitty"
SUBMITTY_DATA_DIR = "/var/local/submitty"
SUBMITTY_REPOSITORY = os.path.join(SUBMITTY_INSTALL_DIR, "GIT_CHECKOUT/Submitty")
MORE_EXAMPLES_DIR = os.path.join(SUBMITTY_INSTALL_DIR, "more_autograding_examples")
TUTORIAL_DIR = os.path.join(SUBMITTY_INSTALL_DIR, "GIT_CHECKOUT/Tutorial", "examples")

DB_HOST = "localhost"
DB_PORT = 5432
DB_USER = "submitty_dbuser"
DB_PASS = "submitty_dbuser"

# used for constructing the url to clone repos for vcs gradeables
# with open(os.path.join(SUBMITTY_INSTALL_DIR, "config", "submitty.json")) as submitty_config:
#     submitty_config_json = json.load(submitty_config)
SUBMISSION_URL = 'submitty_config_json["submission_url"]'
VCS_FOLDER = os.path.join(SUBMITTY_DATA_DIR, 'vcs', 'git')

DB_ONLY = False
NO_SUBMISSIONS = False
NO_GRADING = False

NOW = dateutils.get_current_time()


def main():
    """
    Main program execution. This gets us our commandline arguments, reads in the data files,
    and then sets us up to run the create methods for the users and courses.
    """
    global DB_ONLY, NO_SUBMISSIONS, NO_GRADING
    global DB_HOST, DB_PORT, DB_USER, DB_PASS
    global SUBMITTY_INSTALL_DIR, SUBMITTY_DATA_DIR, SUBMITTY_REPOSITORY
    global MORE_EXAMPLES_DIR, TUTORIAL_DIR

    args = parse_args()
    DB_ONLY = args.db_only
    NO_SUBMISSIONS = args.no_submissions
    NO_GRADING = args.no_grading
    SUBMITTY_INSTALL_DIR = args.install_dir
    SUBMITTY_DATA_DIR = args.data_dir
    SUBMITTY_REPOSITORY = os.path.join(SUBMITTY_INSTALL_DIR, "GIT_CHECKOUT/Submitty")
    MORE_EXAMPLES_DIR = os.path.join(SUBMITTY_INSTALL_DIR, "more_autograding_examples")
    TUTORIAL_DIR = os.path.join(SUBMITTY_INSTALL_DIR, "GIT_CHECKOUT/Tutorial", "examples")

    if not os.path.isdir(SUBMITTY_INSTALL_DIR):
        raise SystemError(f"The following directory does not exist: {SUBMITTY_INSTALL_DIR}")
    if not os.path.isdir(SUBMITTY_DATA_DIR):
        raise SystemError(f"The following directory does not exist: {SUBMITTY_DATA_DIR}")
    for directory in ["courses"]:
        if not os.path.isdir(os.path.join(SUBMITTY_DATA_DIR, directory)):
            raise SystemError("The following directory does not exist: " + os.path.join(
                SUBMITTY_DATA_DIR, directory))
    with open(os.path.join(SUBMITTY_INSTALL_DIR, "config", "database.json")) as database_config:
        database_config_json = json.load(database_config)
        DB_USER = database_config_json["database_user"]
        DB_HOST = database_config_json["database_host"]
        DB_PORT = database_config_json["database_port"]
        DB_PASS = database_config_json["database_password"]
    use_courses = args.course

    # We have to stop all running daemon grading and jobs handling
    # processes as otherwise we end up with the process grabbing the
    # homework files that we are inserting before we're ready to (and
    # permission errors exist) which ends up with just having a ton of
    # build failures. Better to wait on grading any homeworks until
    # we've done all steps of setting up a course.
    print("pausing the autograding and jobs handler daemons")
    os.system("systemctl stop submitty_autograding_shipper")
    os.system("systemctl stop submitty_autograding_worker")
    os.system("systemctl stop submitty_daemon_jobs_handler")
    os.system("systemctl stop submitty_websocket_server")

    courses = {}  # dict[str, Course]
    users = {}  # dict[str, User]
    for course_file in sorted(glob.iglob(os.path.join(args.courses_path, '*.yml'))):
        # only create the plagiarism course if we have a local LichenTestData repo
        if os.path.basename(course_file) == "plagiarism.yml" and not os.path.isdir(os.path.join(SUBMITTY_INSTALL_DIR, "GIT_CHECKOUT", "LichenTestData")):
            continue

        course_json = load_data_yaml(course_file)

        if len(use_courses) == 0 or course_json['code'] in use_courses:
            course = Course(course_json)
            courses[course.code] = course

    create_group("submitty_course_builders")

    for user_file in sorted(glob.iglob(os.path.join(args.users_path, '*.yml'))):
        user = User(load_data_yaml(user_file))
        if user.id in ['submitty_php', 'submitty_daemon', 'submitty_cgi', 'submitty_dbuser', 'vagrant', 'postgres'] or \
                user.id.startswith("untrusted"):
            continue
        user.create()
        users[user.id] = user
        if user.courses is not None:
            for course in user.courses:
                if course in courses:
                    courses[course].users.append(user)
        else:
            for key in courses.keys():
                courses[key].users.append(user)

    # To make Rainbow Grades testing possible, need to seed random to have the same users each time
    random.seed(10090542)

    # we get the max number of extra students, and then create a list that holds all of them,
    # which we then randomly choose from to add to a course
    extra_students = 0
    for course_id in sorted(courses.keys()):
        course = courses[course_id]
        tmp = course.registered_students + course.unregistered_students + \
              course.no_rotating_students + \
              course.no_registration_students
        extra_students = max(tmp, extra_students)
    extra_students = generate_random_users(extra_students, users)

    submitty_engine = create_engine("postgresql:///submitty?host={}&port={}&user={}&password={}"
                                    .format(DB_HOST, DB_PORT, DB_USER, DB_PASS))
    submitty_conn = submitty_engine.connect()
    submitty_metadata = MetaData(bind=submitty_engine)
    user_table = Table('users', submitty_metadata, autoload=True)
    for user_id in sorted(users.keys()):
        user = users[user_id]
        submitty_conn.execute(user_table.insert(),
                              user_id=user.id,
                              user_numeric_id = user.numeric_id,
                              user_password=get_php_db_password(user.password),
                              user_givenname=user.givenname,
                              user_preferred_givenname=user.preferred_givenname,
                              user_familyname=user.familyname,
                              user_preferred_familyname=user.preferred_familyname,
                              user_email=user.email,
                              user_access_level=user.access_level,
                              user_pronouns=user.pronouns,
                              last_updated=NOW.strftime("%Y-%m-%d %H:%M:%S%z"))

    for user in extra_students:
        submitty_conn.execute(user_table.insert(),
                              user_id=user.id,
                              user_numeric_id=user.numeric_id,
                              user_password=get_php_db_password(user.password),
                              user_givenname=user.givenname,
                              user_preferred_givenname=user.preferred_givenname,
                              user_familyname=user.familyname,
                              user_preferred_familyname=user.preferred_familyname,
                              user_email=user.email,
                              user_pronouns=user.pronouns,
                              last_updated=NOW.strftime("%Y-%m-%d %H:%M:%S%z"))

    # INSERT term into terms table, based on today's date.
    today = datetime.today()
    year = str(today.year)
    if today.month < 7:
        term_id    = "s" + year[-2:]
        term_name  = "Spring " + year
        term_start = "01/02/" + year
        term_end   = "06/30/" + year
    else:
        term_id    = "f" + year[-2:]
        term_name  = "Fall " + year
        term_start = "07/01/" + year
        term_end   = "12/23/" + year

    terms_table = Table("terms", submitty_metadata, autoload=True)
    submitty_conn.execute(terms_table.insert(),
                          term_id    = term_id,
                          name       = term_name,
                          start_date = term_start,
                          end_date   = term_end)

    submitty_conn.close()

    for course_id in sorted(courses.keys()):
        course = courses[course_id]
        total_students = course.registered_students + course.no_registration_students + \
            course.no_rotating_students + course.unregistered_students
        students = extra_students[:total_students]
        key = 0
        for i in range(course.registered_students):
            reg_section = (i % course.registration_sections) + 1
            rot_section = (i % course.rotating_sections) + 1
            students[key].courses[course.code] = {"registration_section": reg_section, "rotating_section": rot_section}
            course.users.append(students[key])
            key += 1

        for i in range(course.no_rotating_students):
            reg_section = (i % course.registration_sections) + 1
            students[key].courses[course.code] = {"registration_section": reg_section, "rotating_section": None}
            course.users.append(students[key])
            key += 1

        for i in range(course.no_registration_students):
            rot_section = (i % course.rotating_sections) + 1
            students[key].courses[course.code] = {"registration_section": None, "rotating_section": rot_section}
            course.users.append(students[key])
            key += 1

        for i in range(course.unregistered_students):
            students[key].courses[course.code] = {"registration_section": None, "rotating_section": None}
            course.users.append(students[key])
            key += 1

        course.users.sort(key=lambda x: x.id)

    for course in sorted(courses.keys()):
        courses[course].instructor = users[courses[course].instructor]
        courses[course].check_rotating(users)
        courses[course].create()
        if courses[course].make_customization:
            courses[course].make_course_json()

    # restart the autograding daemon
    print("restarting the autograding and jobs handler daemons")
    os.system("systemctl restart submitty_autograding_shipper")
    os.system("systemctl restart submitty_autograding_worker")
    os.system("systemctl restart submitty_daemon_jobs_handler")
    os.system("systemctl restart submitty_websocket_server")

    if not NO_GRADING:
        # queue up all of the newly created submissions to grade!
        os.system(f"{SUBMITTY_INSTALL_DIR}/bin/regrade.py --no_input {SUBMITTY_DATA_DIR}/courses/")



if __name__ == "__main__":
    main()
