from xml.dom.minidom import TypeInfo
import jstyleson
import subprocess
import sys

f = open(sys.argv[1])
data = jstyleson.load(f)

inst_ext = subprocess.check_output(["code", "--list-extensions"])

inst_ext_str = inst_ext.decode()
for element in data["recommendations"]:
    if inst_ext_str.find(element) != -1:
        continue
    subprocess.check_output(["code", "--install-extension", element])
