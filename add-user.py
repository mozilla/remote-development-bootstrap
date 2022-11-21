import argparse
from collections import namedtuple
import secrets
import string
import sys
import sqlite3
import shutil
import subprocess
import yaml
from schroot_python import chroot


UserProfile = namedtuple("UserProfile", "name pub_key vcs vnc_passwd")

VNC_BASE_PORT = 5907

AUTHORIZED_KEYES_PATH = "/home/developer/.ssh/authorized_keys"


def do_cleanup():
    # TODO: we must delete/ revert everything
    print("Error running previous command!")


def process_shell_command(command, cwd=None):
    print(" ".join(command))
    if subprocess.call(command, cwd=cwd) != 0:
        do_cleanup()
        sys.exit(1)


def process_schroot_command(
    command, schroot: chroot.SchrootChroot, user="developer", dir="/"
):
    print(" ".join(command))
    if schroot.call(command, user=user, dir=dir) != 0:
        do_cleanup()
        sys.exit(1)


def sore_vnc_passwd(vnc_passwd, vnc_passwd_path):
    with open(vnc_passwd_path, "wt") as fh:
        echo_vnc_passwd_proc = subprocess.Popen(
            ["echo", vnc_passwd], stdout=subprocess.PIPE
        )
        gen_store_vnc_passwd = subprocess.Popen(
            ["vncpasswd", "-f"], stdin=echo_vnc_passwd_proc.stdout, stdout=fh
        )
        gen_store_vnc_passwd.communicate()


def config_bash_cfg(profile_id, profile_name):
    with open("./config/bash.cfg", "r+t") as fh:
        port = VNC_BASE_PORT + profile_id
        config = fh.read().format(PORT=str(port))

        with open(
            "/srv/mozilla/" + profile_name + "/home/developer/.bashrc", "w+t"
        ) as fh_bash:
            fh_bash.write(config)


def gen_vnc_passwd() -> string:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for i in range(10))


def update_authorized(profile: UserProfile):
    with open(AUTHORIZED_KEYES_PATH, "at") as fh:
        fh.write(
            'command="/usr/bin/schroot -c firefox-{name} -d /  -- $SSH_ORIGINAL_COMMAND", {key} developer'.format(
                name=profile.name, key=profile.pub_key
            )
        )


def create_profile(profile: UserProfile):
    conn = sqlite3.connect("profiles.db")

    # Does this user exist?
    query = "select count(*) from users where UNAME='{}'".format(profile.name)
    if conn.execute(query).fetchone()[0] > 0:
        print("User {} already exists, exting!".format(profile.name))
        exit(1)

    # Add user to the DB and prepare it
    query = "INSERT INTO users (UNAME, PUB_KEY, VCS, VNC_PASSWD) VALUES ('{UNAME}', '{PUB_KEY}', '{VCS}', 'NO_PASSWD_YET')".format(
        UNAME=profile.name, PUB_KEY=profile.pub_key, VCS=profile.vcs
    )
    conn.execute(query)
    conn.commit()
    # Get the profile id stored as UID in db
    query = "select UID from users where UNAME='{}'".format(profile.name)
    cursor = conn.execute(query)

    profile_id = 0
    for entry in cursor:
        profile_id = entry[0]

    profile_name = "firefox-{}".format(profile.name)

    directory = "/srv/mozilla/" + profile_name

    command = ["sudo", "mkdir", "-p", directory]
    process_shell_command(command=command)

    command = ["sudo", "debootstrap", "bullseye", directory]
    process_shell_command(command=command)

    directory_chroot = "/etc/schroot/chroot.d/firefox-{}".format(profile.name)

    command = ["sudo", "cp", "-r", "./config/schroot.conf", directory_chroot]
    process_shell_command(command=command)

    # This is not OK but maybe let's store the vnc passwd
    query = "UPDATE users SET VNC_PASSWD = '{VNC_PASSWD}' where UID = {UID}".format(
        UID=str(profile_id), VNC_PASSWD=profile.vnc_passwd
    )

    conn.execute(query)
    conn.commit()

    command = [
        "sudo",
        "sed",
        "--in-place",
        "-e",
        "s/\${USER}/{VALUE}/".format(USER="{USER}", VALUE=profile.name),
        directory_chroot,
    ]
    process_shell_command(command=command)

    with chroot.schroot(profile_name) as local_chroot:
        command = ["mkdir", "-p", "/home/developer"]
        process_schroot_command(command=command, schroot=local_chroot, user="root")

        command = ["chown", "-R", "developer:developer", "/home/developer"]
        process_schroot_command(command=command, schroot=local_chroot, user="root")

        command = ["apt", "install", "sudo", "-y"]
        process_schroot_command(command=command, schroot=local_chroot, user="root")

        command = ["sudo", "cp", "./config/sudoers", directory + "/etc/sudoers"]
        process_shell_command(command=command)

        command = ["sudo", "chown", "root:root", directory + "/etc/sudoers"]
        process_shell_command(command=command)

        command = [
            "apt",
            "install",
            "git",
            "openssh-client",
            "curl",
            "xfce4",
            "xfce4-goodies",
            "tightvncserver",
            "dbus-x11",
            "python3-pip",
            "-y",
        ]
        process_schroot_command(command=command, schroot=local_chroot, user="root")

        # for HG
        if profile.vcs == "hg":
            command = ["hg", "pull", "-u"]
            process_shell_command(command=command, cwd="/srv/mozilla/mozilla-unified")

            command = [
                "cp",
                "-r",
                "mozilla-unified",
                profile_name + "/home/developer",
            ]
            process_shell_command(command=command, cwd="/srv/mozilla")

            command = ["sudo", "python3", "-m", "pip", "install", "mercurial"]
            process_schroot_command(command=command, schroot=local_chroot, user="root")

            command = ["hg", "up", "central"]
            process_schroot_command(
                command=command,
                schroot=local_chroot,
                dir="/home/developer/mozilla-unified/",
            )

        elif profile.vcs == "git":
            command = [
                "curl",
                "https://hg.mozilla.org/mozilla-central/raw-file/default/python/mozboot/bin/bootstrap.py",
                "-O",
            ]
            process_schroot_command(
                command=command,
                schroot=local_chroot,
                dir="/home/developer/",
            )

            command = ["python3 bootstrap.py", "--no-interactive", "--vcs=git"]
            process_schroot_command(
                command=command,
                schroot=local_chroot,
                dir="/home/developer/",
            )
        else:
            print("vcs not recognized! Aborting!")
            sys.exit(1)

        command = [
            "cp",
            "./config/mozconfig",
            directory + "/home/developer/mozilla-unified/.mozconfig",
        ]
        process_shell_command(command=command)

        command = ["./mach", "bootstrap"]
        process_schroot_command(
            command=command,
            schroot=local_chroot,
            dir="/home/developer/mozilla-unified/",
        )

        command = ["./mach", "ide", "vscode"]
        process_schroot_command(
            command=command,
            schroot=local_chroot,
            dir="/home/developer/mozilla-unified/",
        )

        # Configure bash cfg
        config_bash_cfg(profile_id=profile_id, profile_name=profile_name)

        command = ["mkdir", "-p", "/run/user"]
        process_schroot_command(
            command=command,
            schroot=local_chroot,
            user="root",
        )

        command = ["mkdir", "-p", "/run/user/1000"]
        process_schroot_command(
            command=command,
            schroot=local_chroot,
            user="root",
        )

        command = ["chown", "-R", "developer:developer", "/run/user/1000"]
        process_schroot_command(
            command=command,
            schroot=local_chroot,
            user="root",
        )

        command = ["pip3", "install", "jstyleson"]
        process_schroot_command(
            command=command,
            schroot=local_chroot,
        )

        shutil.copy2("./scripts/ext_installer.py", directory + "/home/developer")

        # Copy the rest where it's needed
        shutil.copytree("./config/.vnc", directory + "/home/developer/.vnc")
        print("Store VNC Password {}".format(profile.vnc_passwd))
        sore_vnc_passwd(profile.vnc_passwd, directory + "/home/developer/.vnc/passwd")

        # Process ~/.ssh/authorized_keys
        update_authorized(profile=profile)

        # Let's build now!
        process_schroot_command(
            ["./mach", "build"],
            schroot=local_chroot,
            dir="/home/developer/mozilla-unified/",
        )
    conn.close()


def parse_profile(file_path: str) -> UserProfile:
    with open(file_path, "r") as fh:
        profile = yaml.safe_load(fh)

        # TODO: more checking of the validity of the data!
        return UserProfile(
            name=profile["user"]["name"],
            pub_key=profile["user"]["pub_key"],
            vcs=profile["user"]["vcs"],
            vnc_passwd=gen_vnc_passwd(),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="add-user",
        description="Adds new user environment to the vscote remote dev machine.",
        epilog="Use as: `add-user profile.yml`",
    )
    parser.add_argument("filename")
    args = parser.parse_args()

    # Parse profile from filename
    profile = parse_profile(file_path=args.filename)

    create_profile(profile)
