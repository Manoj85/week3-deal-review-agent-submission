from fastapi import FastAPI
from .schemas import ReviewRequest, ReviewPacket
from .workflow import review

app = FastAPI(title='Loan Review Checkpoint API', version='0.1.0',
    description='Offline sample-format backend slice using fictional policy. No credit decisions.')


@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'offline_sample_parser', 'policy_version': '0.1'}


@app.post('/reviews', response_model=ReviewPacket)
def create_review(request: ReviewRequest):
    return review(request)
