import os
import pathlib
import sys

astibot_src_dir = pathlib.Path(__file__).parent.resolve().parent.resolve()
sys.path.append(os.path.join(astibot_src_dir, 'vendor'))
