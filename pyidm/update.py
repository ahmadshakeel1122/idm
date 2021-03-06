"""
    pyIDM

    multi-connections internet download manager, based on "LibCurl", and "youtube_dl".

    :copyright: (c) 2019-2020 by Mahmoud Elshahat.
    :license: GNU LGPLv3, see LICENSE for more details.
"""

# todo: change docstring to google format and clean unused code
# check and update application

import hashlib
import json
import py_compile
import shutil
import sys
import zipfile, tarfile
import queue
import time
from threading import Thread
from distutils.dir_util import copy_tree
import os
import webbrowser
from packaging.version import parse as parse_version

from . import config
from .utils import log, download, run_command, delete_folder, version_value, delete_file


def update():
    """
    download update patch and update current PyIDM files, this is available only for frozen portable version
    for windows
    """

    if config.FROZEN:
        try:
            done = download_update_patch()
            if not done:
                log('Update Failed, check log for more info', showpopup=True)
                return False

            # try to install update patch
            done = install_update_patch()
            if not done:
                log("Couldn't install updates while application running, please restart PyIDM\n\n",
                    'IMPORTANT: when you restart PyIDM it might take around 30 seconds installing updates\n',
                    'before it loads completely\n '
                    'If you see error message just ignore it and start the application again\n', showpopup=True)
                return False
            else:
                log('Update finished successfully, Please restart PyIDM', showpopup=True)
                return True
        except Exception as e:
            log('update()> error', e)
    else:
        open_update_link()


def open_update_link():
    """open browser window with latest release url on github for frozen application or source code url"""
    url = config.LATEST_RELEASE_URL if config.FROZEN else config.APP_URL
    webbrowser.open_new(url)


def check_for_new_version():
    """
    Check for new PyIDM version
    :return: changelog text or None

    FIXME: should use pypi and github api
    """

    # url will be chosen depend on frozen state of the application
    source_code_url = 'https://github.com/pyIDM/pyIDM/raw/master/ChangeLog.txt'
    new_release_url = 'https://github.com/pyIDM/pyIDM/releases/download/extra/ChangeLog.txt'
    url = new_release_url if config.FROZEN else source_code_url

    # download ChangeLog.txt from github,
    log('check for PyIDM latest version ...')

    try:
        buffer = download(url, verbose=False)    # get BytesIO object

        if buffer:
            # convert to string
            changelog = buffer.getvalue().decode()

            # extract version number from contents
            server_version = changelog.splitlines()[0].replace(':', '').strip()

            # update latest version value
            log('Latest server version:', server_version)
            config.APP_LATEST_VERSION = server_version

            # check if this version newer than current application version
            if version_value(server_version) > version_value(config.APP_VERSION):
                log('Latest newer version:', server_version)
                return changelog
    except:
        pass

    return None


def check_for_new_patch():
    """
        download updateinfo.json file to get update patch's info, parse info and return a dict
        :return: dict of parsed info or None

        example contents of updateinfo.json
    {
    "url": "https://github.com/pyIDM/PyIDM/releases/download/2020.5.10/update_for_older_versions.zip",
    "minimum_version": "2020.5.4",
    "max_version": "2020.5.9",
    "sha256": "627FE532E34C8380A63B42AF7D3E533661F845FC4D4F84765897D036EA82C5ED",
    "description": "updated files for versions older than 2020.5.10"
    }

    """

    url = 'https://github.com/pyIDM/pyIDM/releases/download/extra/updateinfo.json'
    info = None

    # get latest update patch url
    log('check for update batches')

    try:
        buffer = download(url, verbose=False)
        if buffer:
            log('decode buffer')
            buffer = buffer.getvalue().decode()  # convert to string
            log('read json information')
            info = json.loads(buffer)

            log('update patch info:', info, log_level=3)

            url = info['url']
            minimum_version = info['minimum_version']
            max_version = info['max_version']
            sha256_hash = info['sha256']
            discription = info['description']

            app_ver, min_ver, max_ver = version_value(config.APP_VERSION), version_value(minimum_version), version_value(max_version)

            if app_ver < min_ver  or app_ver > max_ver:
                info = None

            # check if this patch already installed before, info will be stored in "update_record.info" file
            if os.path.isfile(config.update_record_path):
                with open(config.update_record_path) as file:
                    if sha256_hash in file.read():
                        log('update patch already installed before')
                        info = None
    except Exception as e:
        log('check_for_new_batch()> error,', e)
        info = None

    return info


def download_update_patch():
    """
    download update patch from server
    :return: True if succeeded
    """

    info = check_for_new_patch()

    if info:
        url = info.get('url')
        sha256_hash = info.get('sha256')

        log('downloading "update patch", please wait...')
        target_path = os.path.join(config.current_directory, 'PyIDM_update_files.zip')
        buffer = download(url, file_name=target_path)

        if not buffer:
            log('downloading "update patch", Failed!!!')
            return False

        # check download integrity / hash
        log('Integrity check ....')
        download_hash = hashlib.sha256(buffer.read()).hexdigest()

        # close buffer
        buffer.close()

        if download_hash.lower() != sha256_hash.lower():
            log('Integrity check failed, update patch has different hash, quitting...')
            log('download_hash, original_hash:')
            log('\n', download_hash, '\n', sha256_hash)
            return False
        else:
            log('Integrity check done successfully....')

        # unzipping downloaded file
        log('unzipping downloaded file')
        with zipfile.ZipFile(target_path, 'r') as zip_ref:  # extract zip file
            zip_ref.extractall(config.current_directory)

        log('delete zip file')
        delete_file(target_path, verbose=True)

        # write hash to "update_record.info" file with "append" flag
        log('write hash to file: "update_batches_record"')
        with open(config.update_record_path, 'a') as file:
            file.write('\n')
            file.write(sha256_hash)

        return True


def install_update_patch():
    """
    overwrite current application files with new files from patch update
    note: this function will fail if any file currently in use,
    """
    try:
        log('overwrite old PyIDM files')
        update_patch_path = os.path.join(config.current_directory, 'PyIDM_update_files')
        copy_tree(update_patch_path, config.current_directory)

        log('delete temp files')
        delete_folder(update_patch_path)
        return True
    except Exception as e:
        log('install_update_batch()> error', e)
        return False


# generalize package update
def get_pkg_latest_version(pkg):
    """get latest stable package release version on https://pypi.org/

    url pattern: f'https://pypi.python.org/pypi/{pkg}/json'
    received json will be a dict with:
    keys = 'info', 'last_serial', 'releases', 'urls'
    releases = {'release_version': [{dict for wheel file}, {dict for tar file}], ...}
    dict for tar file = {"filename":"youtube_dlc-2020.10.24.post6.tar.gz", 'url': 'file url'}


    Args:
        pkg (str): package name

    Return:
        2-tuple(str, str): latest_version, and download url
    """

    # download json info
    url = f'https://pypi.python.org/pypi/{pkg}/json'

    # get BytesIO object
    log(f'check for {pkg} latest version on pypi.org...')
    buffer = download(url, verbose=False)
    latest_version = None
    url = None

    if buffer:
        # convert to string
        contents = buffer.getvalue().decode()

        j = json.loads(contents)

        releases = j.get('releases', {})
        if releases:

            latest_version = max([parse_version(release) for release in releases.keys()]) or None
            if latest_version:
                latest_version = str(latest_version)

                # get latest release url
                release_info = releases[latest_version]
                for _dict in release_info:
                    file_name = _dict['filename']
                    url = None
                    if file_name.endswith('tar.gz'):
                        url = _dict['url']
                        break

        return latest_version, url

    else:
        log(f"get_pkg_latest_version() --> couldn't check for {pkg}, url is unreachable")
        return None, None


def update_pkg(pkg, url):
    """updating a package in frozen application folder

    Args:
        pkg (str): package name
        url (str): download url
    """

    current_directory = config.current_directory
    log(f'start updating {pkg}')

    # check if the application is frozen, e.g. runs from a windows cx_freeze executable
    # if run from source, we will update system installed package and exit
    if not config.FROZEN:
        cmd = f'"{sys.executable}" -m pip install {pkg} --upgrade'
        success, output = run_command(cmd)
        if success:
            log(f'successfully updated {pkg}, please restart application', showpopup=True)
        return

    # paths
    temp_folder = os.path.join(current_directory, f'temp_{pkg}')
    extract_folder = os.path.join(temp_folder, 'extracted')
    tar_fn = f'{pkg}.tar.gz'
    tar_fp = os.path.join(temp_folder, tar_fn)

    target_pkg_folder = os.path.join(current_directory, f'lib/{pkg}')
    bkup_folder = os.path.join(current_directory, f'lib/{pkg}_bkup')
    new_pkg_folder = None

    # make temp folder
    log('making temp folder in:', current_directory)
    if not os.path.isdir(temp_folder):
        os.mkdir(temp_folder)

    def bkup():
        # backup current youtube-dl module folder
        log(f'delete previous backup and backup current {pkg}:')
        delete_folder(bkup_folder)
        shutil.copytree(target_pkg_folder, bkup_folder)

    def extract():
        with tarfile.open(tar_fp, 'r') as tar:
            tar.extractall(path=extract_folder)

    def compile_file(q):
        while q.qsize():
            file = q.get()

            if file.endswith('.py'):
                try:
                    py_compile.compile(file, cfile=file + 'c')
                    os.remove(file)
                except Exception as e:
                    log('compile_file()> error', e)
            else:
                print(file, 'not .py file')

    def compile_all():
        q = queue.Queue()

        # get files list and add it to queue
        for item in os.listdir(new_pkg_folder):
            item = os.path.join(new_pkg_folder, item)

            if os.path.isfile(item):
                file = item
                # compile_file(file)
                q.put(file)
            else:
                folder = item
                for file in os.listdir(folder):
                    file = os.path.join(folder, file)
                    # compile_file(file)
                    q.put(file)

        tot_files_count = q.qsize()
        last_percent_value = 0

        # create 10 worker threads
        threads = []
        for _ in range(10):
            t = Thread(target=compile_file, args=(q,), daemon=True)
            threads.append(t)
            t.start()

        # watch threads until finished
        while True:
            live_threads = [t for t in threads if t.is_alive()]
            processed_files_count = tot_files_count - q.qsize()
            percent = processed_files_count * 100 // tot_files_count
            if percent != last_percent_value:
                last_percent_value = percent
                log('#', start='', end='' if percent < 100 else '\n')

            if not live_threads and not q.qsize():
                break

            time.sleep(0.1)
        log('Finished compiling to .pyc files')

    def overwrite_pkg():
        delete_folder(target_pkg_folder)
        shutil.move(new_pkg_folder, target_pkg_folder)
        log('new package copied to:', target_pkg_folder)

    # start processing -------------------------------------------------------
    log(f'start updating {pkg} please wait ...')

    try:
        # use a thread to show some progress while backup
        t = Thread(target=bkup)
        t.start()
        while t.is_alive():
            log('#', start='', end='')
            time.sleep(0.3)

        log('\n', start='')

        # download from pypi
        log(f'step 1 of 4: downloading {pkg} raw files')
        buffer = download(url, file_name=tar_fp)
        if not buffer:
            log(f'failed to download {pkg}, abort update')
            return

        # extract tar file
        log(f'step 2 of 4: extracting {tar_fn}')

        # use a thread to show some progress while unzipping
        t = Thread(target=extract)
        t.start()
        while t.is_alive():
            log('#', start='', end='')
            time.sleep(0.3)

        log('\n', start='')
        log(f'{tar_fn} extracted to: {temp_folder}')

        # define new pkg folder
        pkg_master_folder = os.path.join(extract_folder, os.listdir(extract_folder)[0])
        new_pkg_folder = os.path.join(pkg_master_folder, pkg)

        # compile files from py to pyc
        log('step 3 of 4: compiling files, please wait')
        compile_all()

        # delete old youtube-dl module and replace it with new one
        log(f'step 4 of 4: overwrite old {pkg} files')
        overwrite_pkg()

        # clean old files
        log('delete temp folder')
        delete_folder(temp_folder)
        log(f'{pkg} ..... done updating \nplease restart Application now', showpopup=True)
    except Exception as e:
        log(f'update_pkg()> error', e)


def rollback_pkg_update(pkg):
    """rollback last package update

    Args:
        pkg (str): package name
    """
    if not config.FROZEN:
        log(f'rollback {pkg} update is currently working on portable windows version only')
        return

    log(f'rollback last {pkg} update ................................')

    # paths
    current_directory = config.current_directory
    target_pkg_folder = os.path.join(current_directory, f'lib/{pkg}')
    bkup_folder = os.path.join(current_directory, f'lib/{pkg}_bkup')

    try:
        # find a backup first
        if os.path.isdir(bkup_folder):
            log(f'delete active {pkg} module')
            delete_folder(target_pkg_folder)

            log(f'copy backup {pkg} module')
            shutil.copytree(bkup_folder, target_pkg_folder)

            log(f'Done restoring {pkg} module, please restart Application now', showpopup=True)
        else:
            log(f'No {pkg} backup found')

    except Exception as e:
        log('rollback_pkg_update()> error', e)




