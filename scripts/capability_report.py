"""Print installed processing capabilities without reading any personal media."""
import json,platform
from openphoto import imaging,media,native

def report():
    result={'app':'LiquidFrame','version':'0.2.0','platform':platform.system(),'python':platform.python_version(),'tools':media.capabilities(),'native':native.capabilities(),'formats':imaging.formats(),'verification':'Installed capability discovery; consult VERIFICATION.md for exercised operations.','limitations':['HDR processing is not verified.','Physical-device and camera modes require separate validation.','Windows/Linux CI is configured but not executed in this local session.']}
    return result
if __name__=='__main__':print(json.dumps(report(),indent=2))
