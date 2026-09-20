"""Runtime readiness and private Drive persistence."""
import importlib.util
import json
import os
from pathlib import Path


def doctor():
    packages={'prices':'FinanceDataReader','kr_flows':'pykrx','dart':'OpenDartReader','google':'google.auth','gpt':'openai'}
    installed={}
    for k,p in packages.items():
        try:installed[k]=importlib.util.find_spec(p) is not None
        except ModuleNotFoundError:installed[k]=False
    return {'packages':installed,'credentials':{k:bool(os.getenv(k)) for k in ['SEC_USER_AGENT','DART_API_KEY','OPENAI_API_KEY','OPENAI_MODEL','GOOGLE_APPLICATION_CREDENTIALS']},
            'note':'Presence is not authentication. Run the desired provider and verify its output. Credential values are never displayed.'}


def backup_drive(directory,folder_id):
    """Upload result/report files to an explicitly configured private Drive folder."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials,_=google.auth.default(scopes=['https://www.googleapis.com/auth/drive.file'])
    session=AuthorizedSession(credentials)
    # Resolve target before writes, never search for or guess a folder.
    r=session.get(f'https://www.googleapis.com/drive/v3/files/{folder_id}',params={'fields':'id,mimeType','supportsAllDrives':'true'},timeout=30)
    r.raise_for_status()
    if r.json()['mimeType']!='application/vnd.google-apps.folder':raise ValueError('Backup destination must be a Drive folder')
    outputs=[]
    for path in Path(directory).iterdir():
        if path.suffix not in ('.json','.md'):continue
        boundary='pepper-upload-boundary'
        meta={'name':Path(directory).name+'-'+path.name,'parents':[folder_id]}
        body=(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+json.dumps(meta)+
              f'\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+path.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
        r=session.post('https://www.googleapis.com/upload/drive/v3/files',params={'uploadType':'multipart','supportsAllDrives':'true'},
                       headers={'Content-Type':f'multipart/related; boundary={boundary}'},data=body,timeout=60)
        r.raise_for_status();outputs.append(r.json()['id'])
    return outputs


def restore_drive(folder_id,root='data/runs'):
    """Restore at most 100 recent run snapshots for ephemeral scheduled runners."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    if not folder_id or not all(c.isalnum() or c in '_-' for c in folder_id):raise ValueError('Invalid folder ID')
    credentials,_=google.auth.default(scopes=['https://www.googleapis.com/auth/drive.file'])
    session=AuthorizedSession(credentials)
    response=session.get('https://www.googleapis.com/drive/v3/files',params={
        'q':f"'{folder_id}' in parents and trashed=false and name contains '-result.json'",
        'fields':'files(id,name)','pageSize':100,'orderBy':'createdTime desc','supportsAllDrives':'true','includeItemsFromAllDrives':'true'},timeout=30)
    response.raise_for_status();count=0
    for file in response.json().get('files',[]):
        if not file['name'].endswith('-result.json'):continue
        r=session.get(f'https://www.googleapis.com/drive/v3/files/{file["id"]}',params={'alt':'media'},timeout=30)
        r.raise_for_status();value=r.json()
        if not all(k in value for k in ('asof','instruments','coverage','generated_at')):continue
        dest=Path(root)/('restored-'+file['id']);dest.mkdir(parents=True,exist_ok=True)
        (dest/'result.json').write_text(json.dumps(value,ensure_ascii=False,allow_nan=False));count+=1
    return count
