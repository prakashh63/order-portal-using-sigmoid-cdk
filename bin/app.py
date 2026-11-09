import os

from app_config import build_config
from sigmoid_cdk import SigmoidApp

# The pipeline sets STAGE (dev / staging / prod). Locally it defaults to "dev".
stage = os.environ.get("STAGE", "dev")

app = SigmoidApp(build_config(stage))
app.synth()