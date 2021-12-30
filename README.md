# mkog

Auto install [openGauss](https://opengauss.org/) instance with DCF Cluster mode.

```shell
usage: python3 mkog.py [-h] -c CONFIG [--tarball TARBALL] [-v]

auto install openGauss database(enable DCF mode)

optional arguments:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        mkog config path
  --tarball TARBALL     tarball filepath on local dist. [download online default]
  -v, --version         show mkog version
```


### Configuration

Customize the [config.json](./config.json) file to suit your demand.

```json
{
    "base_dir": "/opt/opengauss",  // 安装目录
    "user": "omm", // 安装系统用户
    "group": "dbgrp",  // 用户组
    "port": 26000,  // 数据库端口
    "dcf_stream_id": 1,  // stream id 区分集群
    "hosts": [ // 集群内机器列表
        {
            "dcf_node_id": 1,  // 自定义节点ID
            "ip": "172.16.0.101",  // 节点IP
            "role": "LEADER"  // 节点初始化角色
        },
        {
            "dcf_node_id": 2,
            "ip": "172.16.0.102",
            "role": "FOLLOWER"
        },
        {
            "dcf_node_id": 3,
            "ip": "172.16.0.103",
            "role": "FOLLOWER"
        }
    ]
}
```

