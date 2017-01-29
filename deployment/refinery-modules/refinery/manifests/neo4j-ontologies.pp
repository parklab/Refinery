class refinery::neo4j-ontologies {
  package { 'unzip':
    name        => 'unzip',
    ensure      => latest,
    require     => Class['apt::update'],
  }
  exec { "stop neo4j service":
    command     => "sudo service neo4j-service stop",
    user        => $app_user,
    group       => $app_group,
    path        => ['/usr/bin/'],
    require     => Service["neo4j-service"],
  }
  exec { "remove old db":
    command     => "sudo rm -rf graph.db",
    cwd         => "/var/lib/neo4j/data/",
    user        => $app_user,
    group       => $app_group,
    path        => ['/usr/bin/'],
    require     => Exec["stop neo4j service"],
  }
  exec { "fetch pre-generated db":
    command     => "sudo wget -q http://data.cloud.refinery-platform.org.s3.amazonaws.com/data/stem-cell-commons/neo4j/2015/graph.db.zip && yes | sudo unzip graph.db.zip",
    cwd         => "/var/lib/neo4j/data/",
    user        => $app_user,
    group       => $app_group,
    path        => ['/usr/bin/'],
    timeout     => 1800,
    require     => [
      Class['neo4j'],
      Package['unzip'],
      Exec["remove old db"]
    ],
  }
  exec { "change db ownership":
    command     => "sudo chown -R neo4j:nogroup /var/lib/neo4j/data/graph.db",
    user        => $app_user,
    group       => $app_group,
    path        => ['/usr/bin/', '/bin/'],
    require     => Exec["fetch pre-generated db"],
  }
  exec { "start neo4j service":
    command     => "sudo service neo4j-service start",
    user        => $app_user,
    group       => $app_group,
    path        => ['/usr/bin/'],
    require     => [Exec["change db ownership"], Service["neo4j-service"]],
  }
  exec { "fetch neo4j fixture":
    command     => "sudo wget -q https://raw.githubusercontent.com/refinery-platform/ontology-imports/master/django-fixure-stemcellcommons.json",
    cwd         => $django_root,
    creates     => "$django_root/django-fixure-stemcellcommons.json",
    path        => ['/usr/bin/'],
    user        => $app_user,
    group       => $app_group,
    timeout     => 1800,
    require     => Exec["start neo4j service"]
  }
  exec { "install neo4j fixture":
    command     => "${virtualenv}/bin/python manage.py loaddata django-fixure-stemcellcommons.json",
    environment => ["DJANGO_SETTINGS_MODULE=${django_settings_module}"],
    cwd         => $django_root,
    user        => $app_user,
    group       => $app_group,
    require     => [
      Exec["fetch neo4j fixture"],
      Exec["start neo4j service"],
      Python::Requirements[$requirements],
      Postgresql::Server::Db["refinery"]
    ],
  }
  exec { "install neo4j annotations":
    command     => "${virtualenv}/bin/python manage.py import_annotations -c",
    environment => ["DJANGO_SETTINGS_MODULE=${django_settings_module}"],
    cwd         => $django_root,
    user        => $app_user,
    group       => $app_group,
    require     => Exec["install neo4j fixture"],
  }
  exec { "remove neo4j fixture":
    command     => "rm -rf django-fixure-stemcellcommons.json",
    cwd         => $django_root,
    user        => $app_user,
    group       => $app_group,
    path        => ['/bin/'],
    require     => Exec["install neo4j annotations"],
  }

}