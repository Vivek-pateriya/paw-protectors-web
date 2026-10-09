import os
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo

load_dotenv()
if __name__=='__main__':
    Path('artifacts').mkdir(exist_ok=True)
    env=os.environ.copy()
    env['TEST_DATABASE_URL']=os.getenv('TEST_DATABASE_URL',make_conninfo(os.environ['DATABASE_URL'],dbname='paw_test'))
    subprocess.run([sys.executable,'-m','pytest','tests','-v','--junitxml=artifacts/pytest.xml'],env=env,check=True)
    subprocess.run([sys.executable,'-m','scripts.dbms_demo'],env=env,check=True)
    subprocess.run([sys.executable,'-m','scripts.benchmark'],env=env,check=True)
