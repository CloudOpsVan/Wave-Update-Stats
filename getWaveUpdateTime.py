import time
import json
import sys

import math

import cic
import datetime
from pprint import pprint
import urllib2, base64

username = ''
password = ''

file_path = 'C:\Users\I852047\OneDrive - SAP SE\FPA35\Wave Update\Jenkins analysis\\'
epm_log_file = 'epm log.json'
fpa_log_file = 'fpa log.json'

print_time = bool(0)
group_info = {}


def read_json_data(json_file):
    with open(file_path + json_file) as data_file:
        json_data = json.load(data_file)
    return json_data


def write_json_to_file(json_data, json_file):
    with open(file_path + json_file, 'w') as outfile:
        json.dump(json_data, outfile)


def get_authentication():
    f = open("authentication\\account.txt", "r")
    line = f.readline()
    global username
    global password
    username,password = line.strip().split(':')
    f.close()


def get_all_epm_builds():
    start = time.time()
    url = 'https://vandevopsjenkins01.pgdev.sap.corp/job/Cloud/job/HCP_Component_Update/api/json?depth=2&' \
          'pretty=true&tree=allBuilds[number,timestamp,duration,actions[parameters[name,value]]]'

    request = urllib2.Request(url)
    base64string = base64.b64encode('%s:%s' % (username, password))
    request.add_header("Authorization", "Basic %s" % base64string)
    result = urllib2.urlopen(request)
    builds = json.loads(result.read().decode())

    write_json_to_file(builds, epm_log_file)
    index = epm_log_file.find('.json')
    origin_log_file = epm_log_file[:index] + ' - origin' + epm_log_file[index:]
    write_json_to_file(builds, origin_log_file)

    if print_time:
        print("Got all builds in: {} s".format(int(time.time() - start)))
    return builds


def get_all_fpa_builds():
    start = time.time()
    url = 'https://vandevopsjenkins01.pgdev.sap.corp/job/Cloud/job/Cloud_system_admin/api/json?depth=2&' \
          'pretty=true&tree=allBuilds[number,timestamp,duration,actions[parameters[name,value]]]'

    request = urllib2.Request(url)
    base64string = base64.b64encode('%s:%s' % (username, password))
    request.add_header("Authorization", "Basic %s" % base64string)
    result = urllib2.urlopen(request)
    builds = json.loads(result.read().decode())

    write_json_to_file(builds, fpa_log_file)
    index = fpa_log_file.find('.json')
    origin_log_file = fpa_log_file[:index] + ' - origin' + fpa_log_file[index:]
    write_json_to_file(builds, origin_log_file)

    if print_time:
        print("Got all builds in: {} s".format(int(time.time() - start)))
    return builds


def pre_process_data(json_data, file_name):
    start = time.time()
    for build in json_data['allBuilds']:
        actions = build['actions']
        for i in range(len(actions) - 1, -1, -1):
            if 'parameters' in build['actions'][i]:
                parameters = build['actions'][i]['parameters']
                for j in range(len(parameters) - 1, -1, -1):
                    param = parameters[j]
                    if param['name'] == 'SAP_PASSWORD' or param['name'] == 'HANA_PASSWORD':
                        del parameters[j]
                    if param['name'] == 'INSTANCE' or param['name'] == 'FPA_DU_DIR' or param['name'] == 'EPM_VERSION':
                        build[param['name'].lower()] = param['value']
                        if param['name'] == 'EPM_VERSION':
                            build['version'] = param['value']
                        elif param['name'] == 'FPA_DU_DIR':
                            index = param['value'].rfind('/')
                            build['version'] = param['value'][index + 1:]
            else:
                del build['actions'][i]

    write_json_to_file(json_data, file_name)
    if print_time:
        print("Pre-process the data in: {} s".format(int(time.time() - start)))
    return json_data


def filter_builds_by_system_version(build_list, ins, ver):
    builds = []
    for build in build_list['allBuilds']:
        if build['instance'] == ins and build['version'] == ver:
            builds.append(build)
    # pprint(builds)

    write_json_to_file(builds, ins + ' - ' + ver + '.json')
    return builds


def filter_builds_by_group_version(build_list, group, ver):
    start = time.time()
    instances = group_info[group]
    builds = []
    invalid_builds = []
    for build in build_list['allBuilds']:
        if 'version' not in build or 'instance' not in build:
            invalid_builds.append(build)
        elif build['version'] == ver and build['instance'] in instances:
            builds.append(build)
    # pprint(builds)

    write_json_to_file(invalid_builds, group + ' - ' + ver + ' - invalid.json')
    write_json_to_file(builds, group + ' - ' + ver + '.json')
    if print_time:
        print("Filter by group in: {} s".format(int(time.time() - start)))
    return builds


# This method is currently not used, keep it just for reference
def get_fpa_dir(ver):
    return '/net/build-drops-wdf/dropzone/orca/EPM_FPA/rel/' + ver


def build_group_info():
    start = time.time()
    group_information = {}
    groups = ['Group1-EU', 'Group1-AP', 'Group1-US', 'Group2-EU', 'Group2-AP', 'Group2-US',
              'Group3-EU', 'Group3-AP', 'Group3-US']

    cic_user = username
    cic_password = password
    cic_url = "https://cic.mo.sap.corp"
    cic_obj = cic.CicDaO(cic_user, cic_password, cic_url)
    result = cic_obj.getInstanceList()

    for i in result:
        if i["details"]["updateGroup"] in groups:
            group_information.setdefault(i["details"]["updateGroup"], []).append(i["details"]["name"])

    write_json_to_file(group_information, 'group info.json')
    if print_time:
        print("Build group info in: {} s".format(int(time.time() - start)))
    return group_information


# This method is currently not used, keep it just for reference
def get_group_list(update_group):
    start = time.time()
    cic_user = username
    cic_password = password
    cic_url = "https://cic.mo.sap.corp"
    cic_obj = cic.CicDaO(cic_user, cic_password, cic_url)
    filter_set = {"updateGroup": update_group}
    keyword = ["name", "updateGroup"]
    result = cic_obj.getSystemsByFilter(filter_set, keyword)
    instances = []
    for i in result:
        instances.append(i["details"]["name"])
    if print_time:
        print("Get group list in: {} s".format(int(time.time() - start)))
    return instances


def find_first_started(builds):
    start = time.time()
    first_started = sys.maxint
    first_build = {}
    for build in builds:
        started = build['timestamp'] / 1000
        first_started = min(started, first_started)
        if first_started == started:
            first_build = build
    first_started = datetime.datetime.fromtimestamp(first_started)
    print first_started
    # pprint(first_build)
    if print_time:
        print("Find first build in: {} s".format(int(time.time() - start)))
    return first_started


def find_last_finished(builds):
    start = time.time()
    last_finished = 0
    for build in builds:
        finished = (long(build['timestamp']) + build['duration']) / 1000
        last_finished = max(finished, last_finished)
    last_finished = datetime.datetime.fromtimestamp(last_finished)
    print last_finished
    if print_time:
        print("Find last build in: {} s".format(int(time.time() - start)))
    return last_finished


def get_group_update_time(fpa_builds, fpa_ver, epm_builds, epm_ver, group):
    fpa_builds = filter_builds_by_group_version(fpa_builds, group, fpa_ver)
    epm_builds = filter_builds_by_group_version(epm_builds, group, epm_ver)
    if fpa_builds == [] or epm_builds == []:
        print "Cannot find any build"
    first_epm = find_first_started(epm_builds)
    last_fpa = find_last_finished(fpa_builds)
    print("Total " + group + " update time for wave " + fpa_ver + ": {} min"
          .format(math.ceil((last_fpa - first_epm).total_seconds() / 60)))


def get_system_update_time(fpa_builds, fpa_ver, epm_builds, epm_ver, ins):
    fpa_builds = filter_builds_by_system_version(fpa_builds, ins, fpa_ver)
    epm_builds = filter_builds_by_system_version(epm_builds, ins, epm_ver)
    if fpa_builds == [] or epm_builds == []:
        print "Cannot find any build"
    first_epm = find_first_started(epm_builds)
    last_fpa = find_last_finished(fpa_builds)
    print(ins + " update time for wave " + fpa_ver + ": {} min"
          .format(math.ceil((last_fpa - first_epm).total_seconds() / 60)))


if __name__ == '__main__':
    execution_start = time.time()

    # Get Jenkins logs and preprocess the data
    get_authentication()
    get_all_epm_builds()
    get_all_fpa_builds()
    pre_process_data(read_json_data(fpa_log_file), fpa_log_file)
    pre_process_data(read_json_data(epm_log_file), epm_log_file)
    group_info = build_group_info()

    # Analyze the logs
    group_info = read_json_data('group info.json')
    all_fpa_builds = read_json_data(fpa_log_file)
    all_epm_builds = read_json_data(epm_log_file)

    groups = ['Group1-AP', 'Group1-EU', 'Group1-US', 'Group2-AP', 'Group2-EU', 'Group2-US']
    # groups = ['Group3-AP', 'Group3-EU', 'Group3-US']
    fpa_version = '2017.21'
    epm_version = '1.00.201721.01'

    for group_name in groups:
        get_group_update_time(all_fpa_builds, fpa_version, all_epm_builds, epm_version, group_name)

    # instances = ['epmprod81']
    # for instance in instances:
    #     get_system_update_time(all_fpa_builds, fpa_version, all_epm_builds, epm_version, instance)

    print("Total execution time: {} s".format(int(time.time() - execution_start)))
