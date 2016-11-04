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

    def _container_opts(self, task):
        opts = ' --name god-' + str(task['id'])
        port_list = []
        if 'ports' in task['requirements']:
            port_list = task['requirements']['ports']
        if task['command']['interactive']:
            port_list.append(22)

        for v in task['container']['volumes']:
            if v['mount'] is None:
                v['mount'] = v['path']
            mode = 'ro'
            if 'acl' in v and v['acl'] == 'rw':
                mode = 'rw'
            opts += ' -v %s:%s:%s' % (v['path'], v['mount'], mode)

        for port in port_list:
            if self.cfg['port_allocate']:
                mapped_port = self.get_mapping_port('godocker-sge', task)
                if mapped_port is None:
                    raise Exception('no port available')
            else:
                mapped_port = port
            task['container']['port_mapping'].append({'host': mapped_port, 'container': port})
            opts += ' -p %s:%s' % (str(mapped_port), str(port))

        opts += ' -c ' + str(task['requirements']['cpu'] * 1024)
        opts += ' -m ' + str(task['requirements']['ram']) + 'g'
        opts += ' ' + task['container']['image']
        opts += ' ' + task['command']['script']
        return opts

    def _qsub(self, task):

        cmd = "#/bin/sh\n"
        cmd += ". %s/god.env\n" % (task['requirements']['sge']['task_dir'])
        cmd += "qsub -N god-%d " % (task['id'])
        if task['requirements']['sge']['queue']:
            cmd += " -q %s " % (task['requirements']['sge']['queue'])
        if task['requirements']['cpu'] > 1:
            cmd += " -pe %s %d" % (task['requirements']['sge']['parallel_env'], task['requirements']['cpu'])
        cmd += " -l h_vmem=%dG" % (task['requirements']['ram'])
        if 'email' in task['requirements'] and task['requirements']['email']:
            cmd += " -m be -M %s" % (task['requirements']['sge']['email'])
        # TODO manage job arrays
        cmd += " -o %s/sge.log -e %s/sge.err " % (task['requirements']['sge']['task_dir'], task['requirements']['sge']['task_dir'])

        cmd += " -wd %s %s/qsub_docker.sh" % (task['requirements']['sge']['task_dir'], task['requirements']['sge']['task_dir'])

        if not self.cfg['placement']['sge']['docker']:
            cmd_content = ''
            with open(task['requirements']['sge']['task_dir']+'/cmd.sh', 'r') as cmd_file:
                cmd_content = cmd_file.read()
            with open(task['requirements']['sge']['task_dir']+'/cmd.sh', 'w') as cmd_file:
                cmd_file.write(cmd)
            os.chmod(task['requirements']['sge']['task_dir']+'/cmd.sh', 0o755)
            with open(task['requirements']['sge']['task_dir']+'/qsub_cmd.sh', 'w') as cmd_file:
                cmd_file.write(cmd_content)
            os.chmod(task['requirements']['sge']['task_dir']+'/qsub_cmd.sh', 0o755)
        else:
            with open(task['requirements']['sge']['task_dir'] + '/qsub_docker.sh', 'w') as qsub_docker:
                docker_url = ''
                if self.cfg['docker']['url']:
                    docker_url = '-H ' + self.cfg['docker']['url']

                container_opts = self._container_opts(task)
                sge_docker = "#!/bin/bash\n"
                sge_docker += "trap \"docker %s stop $containerid; docker %s rm $containerid; exit 1\" SIGHUP SIGINT SIGTERM\n" % (docker_url, docker_url)
                sge_docker += "docker %s pull %s\n" % (docker_url, task['container']['image'])
                sge_docker += "containerid=$(docker %s run -d %s)\n" % (docker_url, container_opts)
                sge_docker += "export containerid\n"
                sge_docker += "while [ 1 -eq 1 ]\n"
                sge_docker += "do\n"
                sge_docker += "RUNNING=$(docker %s inspect --format=\"{{ .State.Running }}\" $containerid 2> /dev/null)\n" % (docker_url)
                sge_docker += "if [ \"$RUNNING\" = \"false\" ]; then\n"
                sge_docker += "    EXITCODE=$(docker %s inspect --format=\"{{ .State.ExitCode }}\" $containerid 2> /dev/null)\n" % (docker_url)
                sge_docker += "    docker %s rm $containerid\n" % (docker_url)
                sge_docker += "    exit $EXITCODE\n"
                sge_docker += "fi\n"
                sge_docker += "sleep 2\n"
                sge_docker += "done\n"
                qsub_docker.write(sge_docker)
            os.chmod(task['requirements']['sge']['task_dir']+'/qsub_docker.sh', 0o755)

            with open(task['requirements']['sge']['task_dir'] + '/qsub_cmd.sh', 'w') as cmd_file:
                cmd_file.write(cmd)
            os.chmod(task['requirements']['sge']['task_dir'] + '/qsub_cmd.sh', 0o755)

        if not self.cfg['placement']['sge']['docker']:
            godocker_sh = None
            with open(os.path.join(task['requirements']['sge']['task_dir'], 'godocker.sh'), 'r') as godocker_sh_file:
                godocker_sh = godocker_sh_file.read().replace('/mnt/go-docker', task['requirements']['sge']['task_dir'])
            if godocker_sh is not None:
                with open(os.path.join(task['requirements']['sge']['task_dir'], 'godocker.sh'), 'w') as godocker_sh_file:
                    godocker_sh_file.write(godocker_sh)

        os.chown(task['requirements']['sge']['task_dir'], task['user']['uid'], task['user']['gid'])
        for root, dirs, files in os.walk(task['requirements']['sge']['task_dir']):
            for task_dir in dirs:
                os.chown(os.path.join(root, task_dir), task['user']['uid'], task['user']['gid'])
            for task_dir in files:
                os.chown(os.path.join(root, task_dir), task['user']['uid'], task['user']['gid'])

        if not self.cfg['placement']['sge']['docker']:
            res = None
            if 'simulate' in self.cfg['placement']['sge'] and self.cfg['placement']['sge']['simulate']:
                res = SIMU_QSUB.replace('#SGEID#', str(task['id']+1000)).replace('#ID#', str(task['id']))
                self.logger.debug('SGE:simulate:would execute: ' + task['requirements']['sge']['task_dir'] + '/godocker.sh')
            else:
                try:
                    res = subprocess.check_output(task['requirements']['sge']['task_dir'] + '/godocker.sh', shell=True)
                except Exception as e:
                    self.logger.error('SGE:Execute:error:' + str(e))
                    return False
            with open(os.path.join(task['requirements']['sge']['task_dir'], 'god.log'), 'r') as god_log:
                res = god_log.read()
            job_id_reg = re.search('job\s+(\d+)', res)
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
            res = None
            try:
                res = subprocess.check_output("su - " + task['user']['id'] + " -c \"" +task['requirements']['sge']['task_dir'] + '/qsub_cmd.sh +"\""', shell=True)
            except Exception as e:
                self.logger.error('SGE:Execute:error:' + str(e))
                return False
            job_id_reg = re.search('job\s+(\d+)', res)
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
                task['container']['status'] = 'qw'
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
            try:
                res = subprocess.check_output(QSTAT, shell=True)
                self.logger.debug('SGE:qstat:'+str(res))
            except Exception:
                self.logger.debug('SGE:qstat:%d:no result' % (task['id']))
                res = None
        if not res:
            # not in qstat, may be pending for scheduling or over
            QACCT = 'su - ' + task['user']['id'] +' -c "qacct -j '+ str(task['container']['id']) + '"'
            res = None
            if 'simulate' in self.cfg['placement']['sge'] and self.cfg['placement']['sge']['simulate']:
                res = SIMU_QACCT.replace('#SGEID#', task['container']['id']).replace('#ID#', str(task['id']))
                self.logger.debug('SGE:simulate:would execute: ' + QACCT)
            else:
                try:
                    res = subprocess.check_output(QACCT, shell=True)
                    self.logger.debug('SGE:qacct:'+str(res))
                except Exception:
                    self.logger.debug('SGE:qacct:%d:no result' % (task['id']))
                    res = None
            if not res:
                # pending for submission
                return (task, False)
            else:
                # In qacct, job is over
                exit_status = re.search('exit_status\s+(\d+)', res)
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
        job_status_reg = re.search(task['user']['id'] + '\s+([qw,Eqw,r,R,d]+)', res)
        if not job_status_reg:
            self.logger.debug('SGE:Status:Unknown:' + str(res))
            return (task, False)
        job_status = None
        job_status = job_status_reg.group(1)
        self.logger.debug('SGE:Status:%d:%s' % (task['id'], str(job_status)))
        node_name_re = re.search('@([a-zA-Z0-9.-]+)\s+', res)
        if node_name_re:
            node_name = node_name_re.group(1)
            task['container']['meta']['Node']['Name'] = node_name
            self.logger.debug('SGE:Node:%d:%s' % (task['id'], str(task['container']['meta']['Node']['Name'])))
            if 'status' not in task['container'] or task['container']['status'] != job_status:
                if 'status' not in task['container']:
                    task['container']['status'] = 'qw'
                self.logger.debug('SGE:Status:%d:switch %s -> %s' % (task['id'], str(task['container']['status']), str(job_status)))
                self.jobs_handler.update({'id': task['id']},
                                                    {'$set': {
                                                        'container.status': job_status,
                                                        'container.meta.Node.Name': node_name
                                                        }
                                                    })
        task['container']['status'] = job_status
        if 'E' in job_status:
            # Error
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
            try:
                subprocess.check_output(QDEL, shell=True)
            except Exception:
                self.logger.debug('SGE:qdel:%d:failed to execute' % (task['id']))
        return (task, True)
