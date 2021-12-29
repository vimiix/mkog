# coding: utf-8

"""mkog.py
    Auto install opengGauss database (enable DCF mode)
"""

import os
import re
import pwd
import grp
import ssl
import platform
import subprocess
import json
import argparse
from urllib import request
from typing import Tuple, List
import logging


TARBALL = "https://opengauss.obs.cn-south-1.myhuaweicloud.com/2.1.0/%s/openGauss-2.1.0-%s-64bit.tar.bz2"
DEFAULT_BASE_DIR = "/opt/opengauss"
DEFAULT_USER = "omm"
DEFAULT_GROUP = "dbgrp"
DEFAULT_PORT = 26000


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")
lg = logging.getLogger()
ssl._create_default_https_context = ssl._create_unverified_context  # diable ca verify


def _exit(msg: str, *args, **kwargs):
    lg.error(msg, *args, **kwargs)
    exit(1)


def _local_ips() -> List[str]:
    """get local host ips

    Returns:
        List[str]: list of local ips
    """
    ipstr = '([0-9]{1,3}\.){3}[0-9]{1,3}'
    res = subprocess.Popen("ifconfig", stdout=subprocess.PIPE)
    output = res.stdout.read()
    ip_pattern = re.compile('(inet %s)' % ipstr)
    if platform == "Linux":
        ip_pattern = re.compile('(inet %s)' % ipstr)
    pattern = re.compile(ipstr)
    ip_list = []
    for ip_addr in re.finditer(ip_pattern, str(output)):
        ip = pattern.search(ip_addr.group())
        if ip.group() != "127.0.0.1":
            ip_list.append(ip.group())
    if not ip_list:
        _exit("not found local ips")
    return ip_list


class Host:

    def __init__(self, dcf_node_id: int, ip: str, role: str) -> None:
        self.dcf_node_id = dcf_node_id
        self.ip = ip
        self.role = role


class Config:

    def __init__(self, filepath: str) -> None:
        if not os.path.exists(filepath):
            _exit("config file '%s' not exists", filepath)

        with open(filepath, 'r') as f:
            d = json.load(f)
        self.base_dir = d.get('base_dir') or DEFAULT_BASE_DIR
        self.user = d.get('user') or DEFAULT_USER
        self.group = d.get('group') or DEFAULT_GROUP
        self.port = d.get('port') or DEFAULT_PORT
        self.dcf_stream_id = d.get('dcf_stream_id') or 1
        if not d.get('hosts'):
            _exit("config error: hosts required")
        self.hosts = [Host(h['dcf_node_id'], h['ip'], h['role'])
                      for h in d['hosts']]

    def host_ips(self) -> List[str]:
        return [h.ip for h in self.hosts]


def fetch_tarball_online() -> str:
    """Download openGauss install package from obs

    Returns:
        str: tarball file path on local disk
    """
    machine = platform.machine()
    lg.info("machine type: %s", machine)
    if machine not in ('x86_64', 'aarch64'):
        _exit("invalid machine type")

    dist = platform.dist() or "openEuler"  # arm机器上获取为空
    lg.info("distribution: %s", dist)
    if machine == 'x86_64':
        if dist == 'centos':
            tarball_url = TARBALL % ('x86', 'CentOS')
        else:
            tarball_url = TARBALL % ('x86_openEuler', 'openEuler')
    else:
        tarball_url = TARBALL % ('arm', 'openEuler')

    # download tarball from obs
    lg.info("start download tarball from:\n--> %s", tarball_url)
    tarball_path, _ = request.urlretrieve(tarball_url, )
    return tarball_path


def decompress_tarball(tarball_path: str, pkg_path: str) -> None:
    """decompress openGauss tarball to specified pkg dir

    Args:
        tarball_path (str): openGauss tarball file path
        pkg_path (str): dir path to be installed
    """
    lg.info("try to decompress tarball")
    if not os.path.exists(tarball_path):
        _exit("file '%s' not found", tarball_path)

    if os.system(f"tar -x -f {tarball_path} -C {pkg_path}") != 0:
        _exit("decompress %s to %s failed")


def prepare_directory(base_dir="") -> Tuple[str, str]:
    """prepare openGauss home dir and data dir

    Args:
        base_dir (str, optional): base dir for installing openGauss. 
                                  Defaults to "/opt/opengauss".
    Returns:
        Tuple[str, str]: tuple of home dir and data dir
    """
    lg.info("prepare directory...")
    base_dir = base_dir or DEFAULT_BASE_DIR
    if os.path.exists(base_dir):
        _exit("dir '%s' already exists", base_dir)

    pkg_dir = os.path.join(base_dir, 'pkg')
    data_dir = os.path.join(base_dir, 'data')
    if os.system(f"mkdir -p {pkg_dir}") != 0:
        _exit("mkdir '%s' failed", pkg_dir)
    if os.system(f"mkdir -p {data_dir}") != 0:
        _exit("mkdir '%s' failed", data_dir)

    lg.info("prepare directory successful.\n"
            "home dir is '%s'\n"
            "data dir is '%s'", pkg_dir, data_dir)
    return pkg_dir, data_dir


def confirm_user_and_group(username: str, groupname: str) -> None:
    """ensure that user and group exist and match.
    create them if not exist.

    Args:
        username (str): user name
        groupname (str): group name
    """
    lg.info("check user and group...")
    try:
        group = grp.getgrnam(groupname)
        lg.info("group '%s' already exists")
    except KeyError:
        # group not exists, add it
        lg.info("group '%s' not found, add it", groupname)
        if os.system(f"groupadd {groupname}") != 0:
            _exit("add group '%s' failed", groupname)
    try:
        user = pwd.getpwnam(username)
        if user.pw_gid != group.gr_gid:
            _exit("user '%s' not belongs to group '%s'", username, groupname)
        lg.info("user '%s' already exists")
    except KeyError:
        # user not exists, add it
        lg.info("user '%s' not found, add it", username)
        if os.system(f"useradd -g {groupname} {username}") != 0:
            _exit("add user '%s' failed", username)


def append_env_to_bashrc(username: str, gausshome: str, data_dir: str) -> None:
    """append environment variables required by openGauss to ~/.bashrc

    Args:
        username (str): system user
        gausshome (str): GAUSSHOME env
        data_dir (str): PGDATA env
    """
    lg.info("try to append env to bashrc")
    contents = [
        f"export GAUSSHOME={gausshome}",
        f"export PGDATA={data_dir}",
        "export PATH=$GAUSSHOME/bin:$PATH",
        "export LD_LIBRARY_PATH=$GAUSSHOME/lib:$LD_LIBRARY_PATH"
    ]
    user = pwd.getpwnam(username)
    with open(os.path.join(user.pw_dir, ".bashrc"), 'a') as f:
        f.writelines(contents)
    lg.info("append env to bashrc successful")


def initdb(username: str, gausshome: str, data_dir: str) -> None:
    """init database with gs_initdb

    Args:
        username (str): system username
        gausshome (str): home dir of openGauss
        data_dir (str): data dir of openGauss
    """
    lg.info("start init db...")
    gs_initdb = os.path.join(gausshome, 'bin', 'gs_initdb')
    hostname = platform.node()
    # -c to enable dcf mode
    exit_code = os.system(f"""su - {username}
    -c "{gs_initdb} -c --nodename={hostname} -w og@123456  -D {data_dir}"
    """)
    if exit_code != 0:
        _exit("init db failed")
    lg.info("init db successful")


def modify_hba_conf(data_dir: str, host_ips: List[str]) -> None:
    """append all host ip in cluster to pb_hba.conf

    Args:
        data_dir (str): data dir of openGauss
        host_ips (List[str]): ips of cluster's hosts
    """
    lg.info("start modify pg_hba.conf...")
    fmt = "host\tall\tall\t%s/32\ttrust"
    contents = [fmt % ip for ip in host_ips]
    with open(os.path.join(data_dir, 'pg_hba.conf'), 'a') as f:
        f.writelines(contents)
    lg.info("append all host ip to pb_hba.conf successful")


def modify_postgresql_conf(data_dir: str, cfg: Config) -> None:
    """modify postgresql.conf params for dcf cluster

    Args:
        data_dir (str): data dir of openGauss
        cfg (Config): instance of Config
    """
    lg.info("start modify postgresql.conf params...")
    local_ips = _local_ips()
    local_host = None
    others = []
    for h in cfg.hosts:
        if h.ip in local_ips:
            local_host = h
        else:
            others.append(h)

    if not local_host:
        _exit("not found local host in config file")

    dcf_nodes = []
    for h in cfg.hosts:
        s = '{"stream_id":%d,"node_id":%d,"ip":"%s","port":%d,"role":"%s"}' % (
            cfg.dcf_stream_id, h.dcf_node_id, h.ip, cfg.port+1, h.role
        )
        dcf_nodes.append(s)

    replconninfos = []
    for idx, remote_host in enumerate(others):
        s = "replconninfo%d = 'localhost=%s localport=%d localheartbeatport=%d localservice=%d remotehost=%s remoteport=%d remoteheartbeatport=%d remoteservice=%d'" % (
            idx+1, local_host.ip, cfg.port+2, cfg.port+3, cfg.port+4,
            remote_host.ip, cfg.port+2, cfg.port+3, cfg.port+4,
        )
        replconninfos.append(s)

    contents = [
        f"port = {cfg.port}",
        f"dcf_node_id = {local_host.dcf_node_id}",
        f"dcf_data_path = '{os.path.join(data_dir, 'dcf_data')}'"
        f"dcf_log_path = '{os.path.join(data_dir, 'dcf_log')}'"
        f"dcf_config='[{','.join(dcf_nodes)}]'",
    ]
    contents += replconninfos
    with open(os.path.join(data_dir, 'postgresql.conf'), 'a') as f:
        f.writelines(contents)
    lg.info("update postgresql.conf successful")


def main():
    parser = argparse.ArgumentParser(
        description="auto install openGauss database(enable DCF mode)")
    parser.add_argument('-c', '--config', required=True,
                        dest='config', action='store', help="mkog config path")
    parser.add_argument('--tarball', dest='tarball', action='store',
                        help="tarball filepath on local dist. [download online default]")
    parser.add_argument('-v', '--version', action='version',
                        version='v0.1', help="show mkog version")
    args = parser.parse_args()
    cfg = Config(args.config)

    talball_path = args.tarball or fetch_tarball_online()
    pkg_dir, data_dir = prepare_directory(cfg.base_dir)
    confirm_user_and_group(cfg.user, cfg.group)
    decompress_tarball(talball_path, pkg_dir)
    append_env_to_bashrc(cfg.user, pkg_dir, data_dir)

    if os.system(f"chown -R {cfg.user}:{cfg.group} {cfg.base_dir}") != 0:
        _exit("change dir owner to %s failed", cfg.user)

    initdb(cfg.user, pkg_dir, data_dir)
    modify_hba_conf(data_dir, cfg.host_ips)
    modify_postgresql_conf(data_dir, cfg)


if __name__ == "__main__":
    main()
