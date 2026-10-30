from __future__ import annotations
from pathlib import Path
import argparse,copy,json,os,re,subprocess,sys,tempfile
from contextlib import contextmanager
from guard import check_sources,inspect_content,publication_policy,publication_selection,repository_identity,public_exception,verify_public_content,PublicationPolicyError
BASE=Path(__file__).resolve().parents[1]
REGISTRY=BASE/'references/ambiente-repos.local.json'
GH=Path(os.environ.get('GH_CLI', 'gh'))
SOURCE_SUFFIXES={'.py','.pyw','.sql','.ipynb','.ts','.tsx','.js','.jsx','.css','.html','.json','.yml','.yaml','.toml','.sh','.ps1','.cmd','.bat'}
CODE_DIRS={'src','scripts','tests','sql','notebooks','config','ltv','analise_projeto','prompts','components','public','app','pages','lib','hooks','assets'}
SCAFFOLD={'.gitignore','.gitattributes','README_VERSIONAMENTO.md','project.code-map.json','AGENTS.md','config.portavel.toml'}
CONFIG_NAMES={'package.json','package-lock.json','tsconfig.json','tsconfig.app.json','tsconfig.node.json','components.json','vercel.json','databricks.yml','databricks.yaml','pyproject.toml'}
def run(args,cwd=None,check=False,env=None):
 p=subprocess.run([str(x) for x in args],cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
 if check and p.returncode:raise RuntimeError(p.stderr.strip() or p.stdout.strip())
 return p
class RegistryError(Exception):
 def __init__(self,code):
  self.code=code
  super().__init__(code)

def load():
 try:reg=json.loads(REGISTRY.read_text(encoding='utf-8'))
 except (OSError,ValueError):raise RegistryError('REGISTRY_UNREADABLE_OR_INVALID') from None
 if (not isinstance(reg,dict) or not isinstance(reg.get('github_owner'),str)
     or not reg['github_owner'] or not isinstance(reg.get('projects'),list)):
  raise RegistryError('REGISTRY_UNREADABLE_OR_INVALID')
 ids=[]
 for project in reg['projects']:
  if not isinstance(project,dict) or not isinstance(project.get('id'),str) or not project['id']:
   raise RegistryError('REGISTRY_UNREADABLE_OR_INVALID')
  ids.append(project['id'])
 if len(set(ids))!=len(ids):raise RegistryError('REGISTRY_UNREADABLE_OR_INVALID')
 return reg

@contextmanager
def registry_lock():
 """Short, nonblocking OS file lock shared by writers; never held for network."""
 lock=None
 try:
  lock=REGISTRY.with_name(REGISTRY.name+'.lock').open('a+b')
  lock.seek(0,2)
  if lock.tell()==0:lock.write(b'\0');lock.flush()
  lock.seek(0)
  if os.name=='nt':
   import msvcrt
   msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
  else:
   import fcntl
   fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 except OSError:
  if lock is not None:
   try:lock.close()
   except OSError:pass
  raise RegistryError('REGISTRY_LOCK_UNAVAILABLE') from None
 try:yield
 finally:
  try:
   lock.seek(0)
   if os.name=='nt':
    import msvcrt
    msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
   else:
    import fcntl
    fcntl.flock(lock.fileno(),fcntl.LOCK_UN)
  except OSError:raise RegistryError('REGISTRY_LOCK_RELEASE_FAILED') from None
  finally:
   try:lock.close()
   except OSError:pass

REMOTE_FIELDS={'remote_state','remote_operation','github_url','remote','origin_state'}

def save(reg,project,patch):
 """Merge only owned remote fields into the latest registry, atomically.

    Other writers must use this locking protocol too. This function does not
    accept whole-registry persistence or create a replacement for invalid JSON.
 """
 if not isinstance(patch,dict) or set(patch)-REMOTE_FIELDS:
  raise RegistryError('REGISTRY_PATCH_FIELDS_INVALID')
 temporary=None
 with registry_lock():
  current=load()
  matches=[p for p in current['projects'] if p['id']==project.get('id')]
  if len(matches)!=1:raise RegistryError('REGISTRY_DESTINATION_CONFLICT')
  target=matches[0]
  for source in (target,project):
   if (not isinstance(source.get('github_repo'),str) or not source['github_repo']
       or not isinstance(source.get('repo_root'),str) or not source['repo_root']):
    raise RegistryError('REGISTRY_DESTINATION_CONFLICT')
  if (current['github_owner'].casefold()!=reg.get('github_owner','').casefold()
      or target.get('github_repo','').casefold()!=project.get('github_repo','').casefold()
      or os.path.normcase(os.path.abspath(target.get('repo_root','')))!=os.path.normcase(os.path.abspath(project.get('repo_root','')))
      or target.get('visibility')!=project.get('visibility')
      or current.get('visibility_default')!=reg.get('visibility_default')):
   raise RegistryError('REGISTRY_DESTINATION_CONFLICT')
  identity=project.get('github_repo','').casefold()
  for source in (target,project):
   for key in ('remote','github_url'):
    if source.get(key) and (not isinstance(source[key],str) or repository_identity(source[key])!=identity):
     raise RegistryError('REGISTRY_DESTINATION_CONFLICT')
  effective=copy.deepcopy(patch)
  for key in ('remote','github_url'):
   if effective.get(key) and (not isinstance(effective[key],str) or repository_identity(effective[key])!=identity):
    raise RegistryError('REGISTRY_DESTINATION_CONFLICT')
  if confirmed_push(target):effective.pop('remote_state',None)
  target.update(effective)
  try:
   with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=REGISTRY.parent,
                                    prefix=REGISTRY.name+'.',suffix='.tmp',delete=False) as output:
    temporary=Path(output.name)
    json.dump(current,output,ensure_ascii=False,indent=2)
    output.flush();os.fsync(output.fileno())
   os.replace(temporary,REGISTRY)
   temporary=None
  except (OSError,TypeError,ValueError):
   raise RegistryError('REGISTRY_ATOMIC_WRITE_FAILED') from None
  finally:
   if temporary is not None:
    try:temporary.unlink()
    except OSError:pass
  return copy.deepcopy(target)

def persist_remote(reg,project,patch):
 try:updated=save(reg,project,patch)
 except RegistryError as error:
  return {'id':project['id'],'status':'BLOCKED','code':error.code,
          'operation':'persist_registry','retry_attempted':False}
 project.update(updated)
 return None
def selected(reg,ident):
 if ident=='all':return reg['projects']
 match=[x for x in reg['projects'] if x['id']==ident]
 if not match:raise ValueError('Unknown project ID')
 return match
def local_status(p):
 root=Path(p['repo_root'])
 def g(*a):return run(['git','-C',root,*a]).stdout.strip()
 return {'id':p['id'],'root':str(root),'head':g('rev-parse','--verify','HEAD'),'branch':g('branch','--show-current'),'remote':g('remote','get-url','origin'),'status':g('status','--porcelain=v1','-uno'),'remote_state_recorded':p.get('remote_state','LOCAL_ONLY_NO_REMOTE')}
def scan_project(p):
 root=Path(p['repo_root'])
 r=run(['git','-C',root,'ls-files','--others','--exclude-standard','-z'],check=True)
 files=[x for x in r.stdout.split('\0') if x]
 approved=[];deferred=[]
 for name in files:
  rel=Path(name);parts=rel.parts
  if name in {x['path'] for x in p.get('retained_local_files',[])}:
   deferred.append({'path':name,'issues':['excluded_by_content_review']});continue
  if p['id']=='codex-ambiente':allowed=True
  elif name in SCAFFOLD:allowed=True
  elif p['id']=='revisao-atividades':allowed=False
  elif len(parts)>1 and parts[0] not in CODE_DIRS:allowed=False
  elif rel.suffix.lower() not in SOURCE_SUFFIXES and not rel.name.startswith('requirements'):allowed=False
  elif rel.suffix.lower()=='.json' and rel.name not in CONFIG_NAMES and not rel.name.endswith(('.schema.json','.schema.example.json')):allowed=False
  elif p['id']=='memorias' and parts[0] in {'config','assets'}:allowed=False
  else:allowed=True
  if not allowed:deferred.append({'path':name,'issues':['needs_canonical_or_content_review']});continue
  checks=check_sources(root,[name])
  if checks and checks[0]['issues']:deferred.append(checks[0])
  else:approved.append(name)
 return {'id':p['id'],'root':str(root),'approved_candidates':approved,'deferred':deferred,'scope':'Code/configuration triage; final staged diff must still be reviewed'}
def confirmed_push(p):
 return p.get('remote_state')=='PUSH_CONFIRMED' and bool(re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})',p.get('remote_commit','')))

def remote_block(reg,p,code,operation,preserve_history=False):
 patch={'remote_operation':{'status':'BLOCKED','code':code,'operation':operation,'retry_attempted':False}}
 if not preserve_history and not confirmed_push(p):patch['remote_state']='BLOCKED_'+code
 failed=persist_remote(reg,p,patch)
 if failed:
  failed['cause_code']=code
  return failed
 return {'id':p['id'],'status':'BLOCKED','code':code,'operation':operation,
         'remote_state':p.get('remote_state'),'retry_attempted':False}

def failure_code(status,stdout='',stderr='',operation='lookup'):
 # Classify but never publish raw stderr, headers, URLs or API response excerpts.
 text=(stdout+'\n'+stderr).casefold()
 if status==429 or 'rate limit' in text or 'secondary limit' in text:return 'GITHUB_RATE_LIMIT'
 if operation=='create' and any(x in text for x in ('creation is limited','creation limit','too many repositories','repository creation is currently limited','was submitted too quickly')):
  return 'REPOSITORY_CREATION_LIMIT'
 if status==401:return 'GITHUB_AUTHENTICATION_FAILED'
 if status==403:return 'GITHUB_PERMISSION_DENIED'
 if status is None:return 'GITHUB_TRANSPORT_OR_AMBIGUOUS_ERROR'
 return 'GITHUB_REQUEST_FAILED'

def github_get(endpoint):
 try:response=run([GH,'api',endpoint,'--include','--hostname','github.com'])
 except (OSError,subprocess.TimeoutExpired):return {'status':None,'body':None,'ok':False,'code':'GITHUB_TRANSPORT_OR_AMBIGUOUS_ERROR'}
 stdout=response.stdout.replace('\r\n','\n')
 headers,separator,body=stdout.partition('\n\n')
 match=re.match(r'^HTTP/\S+\s+(\d{3})\b',headers)
 status=int(match.group(1)) if match else None
 try:payload=json.loads(body) if separator else None
 except ValueError:payload=None
 ok=response.returncode==0 and status==200 and isinstance(payload,dict)
 code=None if ok else failure_code(status,response.stdout,response.stderr)
 if status==200 and not ok:code='GITHUB_RESPONSE_INVALID'
 return {'status':status,'body':payload,'ok':ok,'code':code}

def read_origin(root):
 names=run(['git','-C',root,'remote'])
 if names.returncode:raise ValueError('local_repository_unavailable')
 if 'origin' not in names.stdout.splitlines():return None
 result=run(['git','-C',root,'remote','get-url','--all','origin'])
 values=result.stdout.splitlines()
 if result.returncode or len(values)!=1:raise ValueError('origin_configuration_ambiguous')
 pushed=run(['git','-C',root,'remote','get-url','--push','--all','origin'])
 push_values=pushed.stdout.splitlines()
 if pushed.returncode or len(push_values)!=1 or repository_identity(push_values[0])!=repository_identity(values[0]):
  raise ValueError('origin_push_configuration_ambiguous')
 return values[0]

def publication_denial(reg,p,operation='verify_remote',expected_visibility=None):
 """Read the current local decision before remote operations; never infer consent."""
 try:
  current=load()
  policy=publication_policy(current)
  if policy['mode']=='PRIVATE_SELECTED':
   selection=publication_selection(current,p)
   if expected_visibility is not None and selection['visibility']!=expected_visibility:
    raise PublicationPolicyError('PUBLICATION_VISIBILITY_CHANGED')
   if selection['visibility']=='public':
    verify_public_content(Path(p['repo_root']),selection,public_exception(current,selection))
   if operation=='create_remote' and not selection['create_remote']:
    raise PublicationPolicyError('REMOTE_CREATION_NOT_SELECTED')
   return None
  if expected_visibility=='public':
   raise PublicationPolicyError('PUBLICATION_VISIBILITY_CHANGED')
 except (RegistryError,PublicationPolicyError) as error:
  return {'id':p['id'],'status':'BLOCKED','code':error.code,
          'operation':'publication_policy','retry_attempted':False}
 if not policy['create_remote']:
  code='PUBLICATION_LOCAL_ONLY' if policy['mode']=='LOCAL_ONLY' else 'REMOTE_CREATION_DISABLED_BY_POLICY'
  if not any(p.get(key) for key in ('github_repo','remote','github_url')):
   # A local repository has no remote identity to persist or reconcile. Keep its
   # map entry byte-for-byte unchanged rather than fabricating GitHub metadata.
   return {'id':p['id'],'status':'BLOCKED','code':code,'operation':'publication_policy',
           'retry_attempted':False,'persistence':'SKIPPED_NO_REMOTE_BINDING',
           'scope':'Remote provisioning through this helper; not network access control'}
  result=remote_block(reg,p,code,'publication_policy',preserve_history=True)
  result['scope']='Remote provisioning through this helper; not network access control'
  return result
 return None

def ensure_remote(reg,p):
 denied=publication_denial(reg,p)
 if denied:return denied
 try:
  current=load()
  policy=publication_policy(current)
  visibility=publication_selection(current,p)['visibility'] if policy['mode']=='PRIVATE_SELECTED' else 'private'
 except (RegistryError,PublicationPolicyError) as error:
  return {'id':p['id'],'status':'BLOCKED','code':error.code,'operation':'publication_policy','retry_attempted':False}
 def check_scope(operation='verify_remote'):
  return publication_denial(reg,p,operation,expected_visibility=visibility)
 denied=check_scope()
 if denied:return denied
 expected=p.get('github_repo','')
 if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+',expected)
     or expected.split('/')[0].casefold()!=reg.get('github_owner','').casefold()):
  return remote_block(reg,p,'REGISTRY_IDENTITY_INVALID','validate_registry')
 identity=expected.casefold()
 if p.get('remote') and repository_identity(p['remote'])!=identity:
  return remote_block(reg,p,'REGISTRY_REMOTE_MISMATCH','validate_registry')
 root=Path(p['repo_root'])
 try:origin=read_origin(root)
 except (ValueError,OSError,subprocess.TimeoutExpired):
  return remote_block(reg,p,'LOCAL_REPOSITORY_OR_ORIGIN_INVALID','validate_origin')
 if origin is not None and repository_identity(origin)!=identity:
  return remote_block(reg,p,'ORIGIN_IDENTITY_MISMATCH','validate_origin')
 denied=check_scope()
 if denied:return denied
 user=github_get('user')
 if not user['ok']:return remote_block(reg,p,user['code'],'verify_account')
 if str(user['body'].get('login','')).casefold()!=reg['github_owner'].casefold():
  return remote_block(reg,p,'AUTHENTICATED_OWNER_MISMATCH','verify_account')
 denied=check_scope()
 if denied:return denied
 repo=github_get('repos/'+expected)
 if not repo['ok']:
  # A structured 404 is the only absence signal; GraphQL/text failures are ambiguous.
  absent=(repo['status']==404 and isinstance(repo['body'],dict)
          and repo['body'].get('message')=='Not Found')
  if not absent:return remote_block(reg,p,repo['code'],'lookup_repository')
  denied=check_scope('create_remote')
  if denied:return denied
  try:created=run([GH,'repo','create',expected,'--'+visibility,'--description','Codigo e configuracoes do projeto '+p['id']],
                  env=dict(os.environ,GH_HOST='github.com'))
  except (OSError,subprocess.TimeoutExpired):
   return remote_block(reg,p,'GITHUB_TRANSPORT_OR_AMBIGUOUS_ERROR','create_repository')
  if created.returncode:
   status_match=re.search(r'HTTP\s+(\d{3})',created.stderr+'\n'+created.stdout)
   status=int(status_match.group(1)) if status_match else None
   return remote_block(reg,p,failure_code(status,created.stdout,created.stderr,'create'),'create_repository')
  denied=check_scope()
  if denied:return denied
  repo=github_get('repos/'+expected)
  if not repo['ok']:return remote_block(reg,p,repo['code'],'verify_created_repository')
 payload=repo['body']
 if payload.get('private') is not (visibility=='private'):
  return remote_block(reg,p,'REPOSITORY_NOT_PRIVATE' if visibility=='private' else 'REPOSITORY_NOT_PUBLIC','verify_repository')
 if str(payload.get('full_name','')).casefold()!=identity or repository_identity(str(payload.get('html_url','')))!=identity:
  return remote_block(reg,p,'REPOSITORY_IDENTITY_MISMATCH','verify_repository')
 # Re-read immediately before adding so a concurrent origin edit is never replaced.
 denied=check_scope()
 if denied:return denied
 try:
  origin=read_origin(root)
  if origin is not None and repository_identity(origin)!=identity:
   return remote_block(reg,p,'ORIGIN_IDENTITY_MISMATCH','link_origin')
  if origin is None:
   linked=run(['git','-C',root,'remote','add','origin','https://github.com/'+expected+'.git'])
   if linked.returncode:return remote_block(reg,p,'ORIGIN_ADD_FAILED','link_origin')
   origin=read_origin(root)
  if origin is None or repository_identity(origin)!=identity:
   return remote_block(reg,p,'ORIGIN_VERIFICATION_FAILED','link_origin')
 except (ValueError,OSError,subprocess.TimeoutExpired):
  return remote_block(reg,p,'ORIGIN_VERIFICATION_FAILED','link_origin')
 patch={'github_url':payload['html_url'],'remote':origin,'origin_state':'LINKED_VERIFIED',
        'remote_operation':{'status':'VERIFIED','operation':'ensure_remote','retry_attempted':False}}
 if not confirmed_push(p):patch['remote_state']=visibility.upper()+'_REPOSITORY_VERIFIED'
 failed=persist_remote(reg,p,patch)
 if failed:return failed
 return {'id':p['id'],'status':'VERIFIED','url':payload['html_url'],'private':visibility=='private','origin_state':'LINKED_VERIFIED'}
def main():
 a=argparse.ArgumentParser();a.add_argument('command',choices=['status','scan','ensure-remote']);a.add_argument('--project',default='all');a.add_argument('--output')
 args=a.parse_args()
 try:reg=load()
 except RegistryError as error:
  print(json.dumps({'status':'BLOCKED','code':error.code},ensure_ascii=True));return 2
 if args.command=='ensure-remote':
  try:policy=publication_policy(reg)
  except PublicationPolicyError as error:
   print(json.dumps({'status':'BLOCKED','code':error.code},ensure_ascii=True));return 2
  if args.project=='all' and policy['mode']=='PRIVATE_SELECTED':
   print(json.dumps({'status':'BLOCKED','code':'EXPLICIT_PROJECT_REQUIRED'},ensure_ascii=True));return 1
 results=[];limited_by=None
 for p in selected(reg,args.project):
  if limited_by:
   results.append({'id':p['id'],'status':'NOT_ATTEMPTED','code':'ACCOUNT_LIMIT_STOP','blocked_by_project':limited_by,'retry_attempted':False})
   continue
  if args.command=='status':results.append(local_status(p))
  elif args.command=='scan':results.append(scan_project(p))
  else:
   result=ensure_remote(reg,p);results.append(result)
   if {result.get('code'),result.get('cause_code')}&{'GITHUB_RATE_LIMIT','REPOSITORY_CREATION_LIMIT'}:limited_by=p['id']
 text=json.dumps(results,ensure_ascii=False,indent=2)
 if args.output:Path(args.output).write_text(text,encoding='utf-8')
 print(json.dumps({'projects':len(results),'results':results if args.command!='scan' else [{'id':x['id'],'candidates':len(x['approved_candidates']),'deferred':len(x['deferred'])} for x in results]},ensure_ascii=True))
 return 1 if any(x.get('status')=='BLOCKED' for x in results) else 0
if __name__=='__main__':raise SystemExit(main())

