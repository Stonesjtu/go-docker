from godocker.iExecutorPlugin import IExecutorPlugin
import datetime
import iso8601
from godocker.utils import is_array_task
import subprocess
import re
import os

QDEL="qdel -j ${jobid}"

QSTAT="qstat -u '${userid}' | grep ${jobid}"

QACCT="qacct -j ${jobid}"

SIMU_QSUB = "Your job #SGEID# (\"test.sh\") has been submitted"
SIMU_QDEL = "test has deleted job #ID#"
SIMU_QSTAT = "#SGEID# 0.50000 god-#ID# me        r     10/24/2016 00:17:05 test@test.org       1"
SIMU_QEXPLAIN = """==============================================================
job_number:                 #SGEID#
exec_file:                  job_scripts/#SGEID#
submission_time:            Wed Oct 19 16:49:44 2016
owner:                      test
uid:                        1103
group:                      samplegroup
gid:                        1167
sge_o_home:                 /home/me
sge_o_log_name:             xxxx
sge_o_path:                 /usr/local/sge/bin/lx-amd64:/usr/local/bin:/bin:/usr/bin
sge_o_shell:                /bin/tcsh
sge_o_workdir:              /home/me
sge_o_host:                 genocluster2
account:                    sge
cwd:                        /home/me
stderr_path_list:           NONE:NONE:sge.err
mail_list:                  me@test.org
notify:                     FALSE
job_name:                   god-#ID#
jobshare:                   0
shell_list:                 NONE:/bin/bash
env_list:
script_file:                cmd.sh
binding:                    NONE
error reason    1:          10/19/2016 16:49:55 [1103:128801]: execvlp(/data1/sge/default/spool/test/job_scripts/#SGEID#, "/d
scheduling info:            queue instance "genscale.q@cl1n027.genouest.org" dropped because it is temporarily not available
                            queue instance "all.q@test1.genouest.org" dropped because it is temporarily not available
                            queue instance "all.q@test2.genouest.org" dropped because it is disabledd
                            Job is in error state
"""
SIMU_QACCT = """==============================================================
qname        all.q
hostname     test.org
group        testgroup
owner        test
project      NONE
department   defaultdepartment
jobname      test.sh
jobnumber    #SGEID#
taskid       undefined
account      sge
priority     0
qsub_time    Fri Oct 14 07:12:46 2016
start_time   Fri Oct 14 07:12:58 2016
end_time     Fri Oct 14 07:12:58 2016
granted_pe   NONE
slots        1
failed       0
exit_status  0
ru_wallclock 0
ru_utime     0.001
ru_stime     0.004
ru_maxrss    1344
ru_ixrss     0
ru_ismrss    0
ru_idrss     0
ru_isrss     0
ru_minflt    571
ru_majflt    0
ru_nswap     0
ru_inblock   0
ru_oublock   168
ru_msgsnd    0
ru_msgrcv    0
ru_nsignals  0
ru_nvcsw     129
ru_nivcsw    1
cpu          0.005
mem          0.000
io           0.000
iow          0.000
maxvmem      0.000
arid         undefined
"""

class SGE(IExecutorPlugin):

    def get_name(self):
        return "sge"

    def get_type(self):
        return "Executor"

    def features(self):
        '''
        Get supported features

        :return: list of features within ['kill', 'pause', 'cni']
        '''
        return ['kill']

    def set_config(self, cfg):
        self.cfg = cfg


    def run_all_tasks(self, tasks, callback=None):
        '''
        Execute all task list on executor system, all tasks must be executed together

        NOT IMPLEMENTED, will reject all tasks

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        self.logger.error('run_all_tasks not implemented')
        return ([], tasks)

    def _qsub(self, task):
        cmd = "#/bin/sh\n"
        cmd += ". %s/god.env\n" % (task['requirements']['sge']['task_dir'])
        cmd += "qsub -N god-%d " % (task['id'])
        if task['requirements']['sge']['queue']:
            cmd += " -q %s " % (task['requirements']['sge']['queue'])
        if task['requirements']['cpu'] > 1:
            cmd += " -pe %s " % (task['requirements']['sge']['parallel_env'])
        cmd += " -h_vmem=%dG" % (task['requirements']['ram'])
        if 'email' in task['requirements'] and task['requirements']['email']:
            cmd += " -m be -M %s" % (task['requirements']['sge']['email'])
        # TODO manage job arrays
        cmd += " -o %s/sge.log -e %s/sge.err " % (task['requirements']['sge']['task_dir'], task['requirements']['sge']['task_dir'])
        cmd += " -cwd %s %s/qsub_cmd.sh" % (task['requirements']['sge']['task_dir'], task['requirements']['sge']['task_dir'])
        cmd_content = ''
        with open(task['requirements']['sge']['task_dir']+'/cmd.sh', 'r') as cmd_file:
            cmd_content = cmd_file.read()
        with open(task['requirements']['sge']['task_dir']+'/cmd.sh', 'w') as cmd_file:
            cmd_file.write(cmd)
        os.chmod(task['requirements']['sge']['task_dir']+'/cmd.sh', 0o755)
        with open(task['requirements']['sge']['task_dir']+'/qsub_cmd.sh', 'w') as cmd_file:
            cmd_file.write(cmd_content)
        os.chmod(task['requirements']['sge']['task_dir']+'/qsub_cmd.sh', 0o755)

        if not self.cfg['placement']['sge']['docker']:
            res = None
            if 'simulate' in self.cfg['placement']['sge'] and self.cfg['placement']['sge']['simulate']:
                res = SIMU_QSUB.replace('#SGEID#', str(task['id']+1000)).replace('#ID#', str(task['id']))
                self.logger.debug('SGE:simulate:would execute: ' + task['requirements']['sge']['task_dir'] + '/godocker.sh')
            else:
                res = subprocess.check_output(task['requirements']['sge']['task_dir'] + '/godocker.sh', shell=True)
            job_id_reg = re.search('(\d+)', res)
            job_id = None
            if job_id_reg:
                job_id = job_id_reg.group(1)
                self.logger.debug('SGE:Job:New:' + str(job_id))
                task['container']['id'] = str(job_id)
                if 'Node' not in task['container']['meta']:
                    task['container']['meta']['Node'] = {'Name': 'localhost'}
                else:
                    task['container']['meta']['Node']['Name'] = 'localhost'
            else:
                task['status']['reason']  = res
                self.logger.warn('SGE:Job:Error:Failed to submit job ' + str(task['id']))
                return False
            return True
        else:
            task['status']['reason'] = 'Docker support for SGE is not available'
            self.logger.error('Docker support in SGE is not yet supported')
            return False

    def run_tasks(self, tasks, callback=None):
        '''
        Execute task list on executor system

        :param tasks: list of tasks to run
        :type tasks: list
        :param callback: callback function to update tasks status (running/rejected)
        :type callback: func(running list,rejected list)
        :return: tuple of submitted and rejected/errored tasks
        '''
        running_tasks = []
        error_tasks = []
        # for task in tasks:
        for task in tasks:
            task['requirements']['sge'] = {}
            executor_requirements = task['requirements']['executor'].split(':')
            queue = None
            if len(executor_requirements) > 1:
                queue = executor_requirements[1]
            task['requirements']['sge']['queue'] = queue

            email = None
            if task['notify']['email'] and task['user']['email']:
                email = task['notify']['email']
            task['requirements']['sge']['email'] = email

            parallel_env = self.cfg['placement']['sge']['parallel_env']
            task['requirements']['sge']['parallel_env'] = parallel_env

            task_dir = None
            for volume in task['container']['volumes']:
                if volume['name'] == 'go-docker':
                    task_dir = volume['path']
                    break
            task['requirements']['sge']['task_dir'] = task_dir

            if 'meta' not in task['container'] or task['container']['meta'] is None:
                task['container']['meta'] = {}
            if 'Node' not in task['container']['meta'] or task['container']['meta']['Node'] is None:
                task['container']['meta']['Node'] = {}

            is_ok = self._qsub(task)
            if is_ok:
                task['status']['override'] = True
                task['status']['secondary'] = 'qw'
                running_tasks.append(task)
            else:
                self.logger.warn('SGE:Execute:Failed to execute command')
                error_tasks.append(task)
        return (running_tasks, error_tasks)

    def watch_tasks(self, task):
        '''
        Get task status

        :param task: current task
        :type task: Task
        :param over: is task over
        :type over: bool
        '''
        over = False
        finished_date = None
        # exec stat to get status, and qacct if not present in result
        QSTAT='su - ' + task['user']['id'] +' -c "qstat | grep '+ str(task['container']['id']) + ' | grep god"'

        res = None
        if 'simulate' in self.cfg['placement']['sge'] and self.cfg['placement']['sge']['simulate']:
            res = SIMU_QSTAT.replace('#SGEID#', task['container']['id']).replace('#ID#', str(task['id']))
            self.logger.debug('SGE:simulate:would execute: ' + QSTAT)
        else:
            res = subprocess.check_output(QSTAT, shell=True)
        if not res:
            # not in qstat, may be pending for scheduling or over
            QACCT = 'su - ' + task['user']['id'] +' -c "qacct -j '+ str(task['container']['id']) + '"'
            res = None
            if 'simulate' in self.cfg['placement']['sge'] and self.cfg['placement']['sge']['simulate']:
                res = SIMU_QACCT.replace('#SGEID#', task['container']['id']).replace('#ID#', str(task['id']))
                self.logger.debug('SGE:simulate:would execute: ' + QACCT)
            else:
                res = subprocess.check_output(QACCT, shell=True)
            if not res:
                # pending for submission
                return (task, False)
            else:
                # In qacct, job is over
                exit_status = re.search('exit_status\s(\d+)', res)
                if 'State' not in task['container']['meta']:
                    task['container']['meta']['State'] = {}
                exit_code = 1
                try:
                    exit_code = int(exit_status.group(1))
                except Exception as e:
                    self.logger.error('SGE:qacct:%d:%s:Failed to get exit code: %s' % (task['id'], str(task['container']['id']), str(e)))
                task['container']['meta']['State']['ExitCode'] = exit_code

                return (task, True)
        # qstat result, check job status
        if res.startswith('error'):
            if 'State' not in task['container']['meta']:
                task['container']['meta']['State'] = {}
            task['container']['meta']['State']['ExitCode'] = 1
            task['status']['reason'] = res
            return (task, True)
        job_status_reg = re.search('([qw,Eqw,r,R,d]+)', res)
        if not job_status_reg:
            self.logger.debug('SGE:Status:Unknown:' + str(res))
            return (task, False)
        job_status = None
        job_status = job_status_reg.group(1)
        node_name_re = re.search('@([a-zA-Z0-9.-]+)\s+', res)
        node_name = node_name_re.group(1)
        task['container']['meta']['Node']['Name'] = node_name
        if task['container']['status'] != job_status:
            self.jobs_handler.update({'id': task['id']},
                                                {'$set': {
                                                    'container.status': job_status,
                                                    'container.meta.Node.Name': node_name
                                                    }
                                                })
        task['container']['status'] = job_status
        if 'E' in job_status:
            # Error
            # TODO execute a qstat -j X -explain
            if 'State' not in task['container']['meta']:
                task['container']['meta']['State'] = {}
            task['container']['meta']['State']['ExitCode'] = 1
            QEXPLAIN = 'su - ' + task['user']['id'] +' -c "qstat -explain E -j '+ str(task['container']['id']) + '"'
            res = None
            if 'simulate' in self.cfg['placement']['sge'] and self.cfg['placement']['sge']['simulate']:
                res = SIMU_QEXPLAIN.replace('#SGEID#', task['container']['id']).replace('#ID#', str(task['id']))
                self.logger.debug('SGE:simulate:would execute: ' + QEXPLAIN)
            else:
                res = subprocess.check_output(QEXPLAIN, shell=True)
            task['status']['reason'] = 'SGE failed to schedule task: '+str(res)
            self.kill_task(task)
            return (task, True)

        return (task, False)

    def kill_task(self, task):
        '''
        Kills a running task

        :param tasks: task to kill
        :type tasks: Task
        :return: (Task, over) over is True if task could be killed
        '''
        QDEL='su - ' + task['user']['id'] +' -c "qdel -j ' + str(task['container']['id']) + '"'
        res = None
        if 'simulate' in self.cfg['placement']['sge'] and self.cfg['placement']['sge']['simulate']:
            res = SIMU_QDEL.replace('#SGEID#', task['container']['id']).replace('#ID#', str(task['id']))
            self.logger.debug('SGE:simulate:would execute: ' + QDEL)
        else:
            subprocess.check_output(QDEL, shell=True)
        return (task, True)
