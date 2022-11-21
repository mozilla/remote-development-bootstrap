# remote-development-bootstrap #

Script that boot straps a new user on a linux machine, debian compatible, offering Mozilla Firefox build capability alongside VSCode Remote integration.<br />
This program program is very much in BETA state and is not ready for high adoption.

## Basic Principles ##
In order to have multiple user support that are jailed in each environment we use `schroot`.<br />
A general system user is created on the linux machine, `developer`, that is used to bootstrap each additional user in each `chroot` environment by manipulating `~/.ssh/authorized_key`. <br />
All of the generated `users` from one machine are kept in an `sqlite3` database for port tracking of the `VNC` server.<br />
The current `profiles.db` is EMPTY.


## Basic Usage ##
The main tool that is used is `add-user.py` that reads an `yaml` file describing the following details of an user:
* `name`, user name
* `pub_key`, public key for ssh authentication
* `vcs`, git or hg

## External Libraries ##
Python [schroot](https://pypi.org/project/schroot/) was used an imported locally because it needed some modifications to fit our version of Python and needs. All credits go to the respective owner/s of the library.
