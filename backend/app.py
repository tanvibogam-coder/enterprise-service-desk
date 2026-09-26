import os, uuid, hmac, hashlib, base64
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import mysql.connector
from mysql.connector import Error
from flask import Flask, jsonify, request, send_from_directory, g
from flask_cors import CORS
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / 'frontend'
UPLOAD_DIR = Path(__file__).resolve().parent / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)
ALLOWED_UPLOAD_EXTENSIONS = {'pdf','png','jpg','jpeg','gif','doc','docx','xls','xlsx','csv','txt'}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
load_dotenv(Path(__file__).resolve().parent / '.env')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'enterprise-service-desk-dev-secret')
CORS(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

SLA_HOURS = {'Critical': 4, 'High': 8, 'Medium': 24, 'Low': 72}
TRANSITIONS = {
    'Open': ['Assigned', 'In Progress'],
    'Assigned': ['In Progress', 'Pending Information'],
    'In Progress': ['Pending Information', 'Resolved'],
    'Pending Information': ['In Progress'],
    'Resolved': ['Closed'],
    'Closed': []
}


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def db_conn():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '3306')),
        database=os.getenv('DB_NAME', 'enterprise_service_desk'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', '')
    )


def rows(sql, params=()):
    conn = db_conn(); cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params); return cur.fetchall()
    finally:
        cur.close(); conn.close()


def one(sql, params=()):
    data = rows(sql, params); return data[0] if data else None


def execute(sql, params=()):
    conn = db_conn(); cur = conn.cursor()
    try:
        cur.execute(sql, params); conn.commit(); return cur.lastrowid
    finally:
        cur.close(); conn.close()


def execute_many(sql, params_list):
    conn = db_conn(); cur = conn.cursor()
    try:
        cur.executemany(sql, params_list); conn.commit()
    finally:
        cur.close(); conn.close()


def iso(v):
    if v is None: return None
    if isinstance(v, datetime): return v.isoformat(timespec='seconds') + 'Z'
    return v


def token_for(user):
    return serializer.dumps({'sub': user['id'], 'exp': int((datetime.now(timezone.utc)+timedelta(minutes=120)).timestamp())})


def current_user_from_token():
    auth = request.headers.get('Authorization','')
    if not auth.startswith('Bearer '): return None
    token = auth[7:]
    try:
        payload = serializer.loads(token, max_age=120*60)
    except (BadSignature, SignatureExpired): return None
    return one('SELECT id,name,email,role,department,active FROM users WHERE id=%s', (payload.get('sub'),))


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user_from_token()
        if not user or not user['active']:
            return jsonify(error='Authentication required.'), 401
        g.user = user
        return fn(*args, **kwargs)
    return wrapper


def roles(*allowed):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.user['role'] not in allowed: return jsonify(error='You are not authorized.'), 403
            return fn(*args, **kwargs)
        return wrapper
    return deco


def safe_user(u):
    return {'id':u['id'],'name':u['name'],'role':u['role'],'department':u['department'],'email':u['email']}


def sla_state(r):
    deadline = r['slaDeadline']
    if isinstance(deadline,str): deadline = datetime.fromisoformat(deadline.replace('Z',''))
    if r['status'] in ('Resolved','Closed'):
        resolved = r.get('resolvedAt')
        if resolved:
            if isinstance(resolved,str): resolved = datetime.fromisoformat(resolved.replace('Z',''))
        else: resolved = now_utc()
        return 'SLA_MET' if resolved <= deadline else 'SLA_BREACHED_ON_CLOSE'
    remaining = (deadline-now_utc()).total_seconds()
    if remaining < 0: return 'SLA_BREACHED'
    if remaining < 3600: return 'SLA_AT_RISK'
    return 'SLA_ON_TRACK'


def request_obj(r, viewer=None):
    comments = rows('SELECT id,user_id,user_name,role,text,internal,created_at FROM request_comments WHERE request_id=%s ORDER BY created_at,id', (r['id'],))
    if viewer and viewer.get('role') == 'employee':
        comments = [c for c in comments if not c['internal']]
    history = rows('SELECT status,user_id,created_at,note FROM request_history WHERE request_id=%s ORDER BY created_at,id', (r['id'],))
    assignments = rows('SELECT ra.assigned_to, u.name AS assigned_name, ra.assigned_by, ra.assigned_at, ra.note FROM request_assignments ra JOIN users u ON u.id=ra.assigned_to WHERE ra.request_id=%s ORDER BY ra.assigned_at,ra.id', (r['id'],))
    attachments = rows('SELECT id,file_name,file_path,uploaded_by,uploaded_at FROM request_attachments WHERE request_id=%s ORDER BY uploaded_at,id', (r['id'],))
    sla = one('SELECT priority,target_hours,started_at,deadline,completed_at,status FROM sla_records WHERE request_id=%s ORDER BY id DESC LIMIT 1', (r['id'],))
    return {**r,
      'requiredDate': iso(r['required_date']), 'employeeId': r['employee_id'], 'assignedTo': r['assigned_to'],
      'createdAt': iso(r['created_at']), 'updatedAt': iso(r['updated_at']), 'slaDeadline': iso(r['sla_deadline']),
      'resolvedAt': iso(r['resolved_at']),
      'comments':[{'id':c['id'],'by':c['user_id'],'byName':c['user_name'],'role':c['role'],'text':c['text'],'internal':bool(c['internal']),'createdAt':iso(c['created_at'])} for c in comments],
      'history':[{'status':h['status'],'by':h['user_id'],'at':iso(h['created_at']),'note':h['note'] or ''} for h in history],
      'assignments':[{'assignedTo':a['assigned_to'],'assignedName':a['assigned_name'],'assignedBy':a['assigned_by'],'assignedAt':iso(a['assigned_at']),'note':a['note'] or ''} for a in assignments],
      'attachments':[{'id':a['id'],'fileName':a['file_name'],'filePath':a['file_path'],'uploadedBy':a['uploaded_by'],'uploadedAt':iso(a['uploaded_at'])} for a in attachments],
      'slaRecord': ({'priority':sla['priority'],'targetHours':sla['target_hours'],'startedAt':iso(sla['started_at']),'deadline':iso(sla['deadline']),'completedAt':iso(sla['completed_at']),'status':sla['status']} if sla else None),
      'sla': sla_state({**r,'slaDeadline':r['sla_deadline'],'resolvedAt':r['resolved_at']})}


def scope_clause(user):
    if user['role']=='employee': return 'employee_id=%s', [user['id']]
    if user['role'] in ('executive','manager') and user['department'] not in (None,'*'):
        return 'department=%s', [user['department']]
    return '1=1', []


def log_audit(action, request_id=None, details=None):
    execute('INSERT INTO audit_logs(id,user_id,action,request_id,details,created_at) VALUES(%s,%s,%s,%s,%s,%s)',
            ('A-'+uuid.uuid4().hex[:18],g.user['id'],action,request_id,details,now_utc()))


def notify(user_id,message,request_id=None):
    if user_id:
        execute('INSERT INTO notifications(id,user_id,message,request_id,is_read,created_at) VALUES(%s,%s,%s,%s,0,%s)',
                ('N-'+uuid.uuid4().hex[:20],user_id,message,request_id,now_utc()))

@app.get('/api/health')
def health():
    try:
        one('SELECT 1 AS ok')
        return jsonify(status='ok',database='connected',time=iso(now_utc()))
    except Error as e:
        return jsonify(status='error',database='disconnected',error=str(e)), 500

@app.post('/api/auth/login')
def login():
    data=request.get_json(silent=True) or {}; email=data.get('email'); password=data.get('password')
    if not email or not password: return jsonify(error='Email and password are required.'),400
    u=one('SELECT id,name,email,role,department,active,password_hash FROM users WHERE LOWER(email)=LOWER(%s)',(email,))
    if not u or not u['active'] or not check_password_hash(u['password_hash'],password): return jsonify(error='Invalid credentials.'),401
    g.user=u; log_audit('Login',None,f"{u['name']} logged in")
    return jsonify(token=token_for(u),user=safe_user(u))

@app.post('/api/auth/logout')
@auth_required
def logout():
    log_audit('Logout',None,f"{g.user['name']} logged out"); return jsonify(message='Logged out.')

@app.get('/api/auth/me')
@auth_required
def me(): return jsonify(safe_user(g.user))

@app.get('/api/requests')
@auth_required
def list_requests():
    clause, params=scope_clause(g.user); filters=[clause]; vals=list(params)
    for key,col in [('status','status'),('priority','priority'),('department','department'),('category','category'),('assignedTo','assigned_to')]:
        if request.args.get(key): filters.append(f'{col}=%s'); vals.append(request.args.get(key))
    if request.args.get('from'): filters.append('created_at >= %s'); vals.append(request.args['from'].replace('T',' '))
    if request.args.get('to'): filters.append('created_at <= %s'); vals.append(request.args['to'].replace('T',' '))
    q=request.args.get('q')
    if q: filters.append('(LOWER(title) LIKE %s OR LOWER(id) LIKE %s OR LOWER(description) LIKE %s)'); vals += [f'%{q.lower()}%']*3
    sort=request.args.get('sort','-createdAt'); field=sort.lstrip('-'); direction='DESC' if sort.startswith('-') else 'ASC'
    field_map={'createdAt':'created_at','updatedAt':'updated_at','priority':'priority','status':'status','title':'title'}; field=field_map.get(field,'created_at')
    total=one('SELECT COUNT(*) n FROM service_requests WHERE '+' AND '.join(filters),vals)['n']
    p=max(1,int(request.args.get('page',1))); ps=max(1,int(request.args.get('pageSize',10))); offset=(p-1)*ps
    data=rows('SELECT * FROM service_requests WHERE '+' AND '.join(filters)+f' ORDER BY {field} {direction} LIMIT %s OFFSET %s',vals+[ps,offset])
    return jsonify(data=[request_obj(x, g.user) for x in data],total=total,page=p,pageSize=ps,totalPages=(total+ps-1)//ps)

@app.get('/api/requests/<rid>')
@auth_required
def get_request(rid):
    r=one('SELECT * FROM service_requests WHERE id=%s',(rid,));
    if not r:return jsonify(error='Request not found.'),404
    clause,params=scope_clause(g.user)
    if not one('SELECT 1 FROM service_requests WHERE id=%s AND '+clause,(rid,*params)): return jsonify(error='You cannot view this request.'),403
    return jsonify(request_obj(r, g.user))

@app.post('/api/requests')
@auth_required
def create_request():
    is_multipart = bool(
        request.content_type
        and request.content_type.lower().startswith('multipart/form-data')
    )
    upload = request.files.get('attachmentFile') if is_multipart else None
    d = request.form.to_dict() if is_multipart else (request.get_json(silent=True) or {})
    required=['title','category','department','description','priority']
    if any(not str(d.get(x) or '').strip() for x in required):
        return jsonify(error='Title, category, department, description and priority are required.'),400
    if len(d['title'].strip()) > 200 or len(d['description'].strip()) > 5000:
        return jsonify(error='Title must be 200 characters or fewer and description 5000 characters or fewer.'),400
    if d['priority'] not in SLA_HOURS:
        return jsonify(error='Invalid priority.'),400
    cat=one('SELECT name,department,default_priority FROM categories WHERE name=%s',(d['category'],))
    if not cat:
        return jsonify(error='Invalid category.'),400
    if d['department'] != cat['department']:
        return jsonify(error='Department must match the selected category.'),400
    similar=one("SELECT id FROM service_requests WHERE employee_id=%s AND category=%s AND status NOT IN ('Resolved','Closed') AND created_at >= %s ORDER BY created_at DESC LIMIT 1",(g.user['id'],d['category'],now_utc()-timedelta(days=3)))
    created=now_utc()
    max_id=one("SELECT COALESCE(MAX(CAST(SUBSTRING(id,5) AS UNSIGNED)),1000) AS n FROM service_requests")['n']
    rid='REQ-'+str(int(max_id)+1)
    deadline=created+timedelta(hours=SLA_HOURS[d['priority']])
    attachment_name = None
    stored_path = None
    if upload and upload.filename:
        attachment_name = secure_filename(upload.filename)
        if not attachment_name:
            return jsonify(error='Invalid attachment filename.'),400
        ext = attachment_name.rsplit('.',1)[-1].lower() if '.' in attachment_name else ''
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            return jsonify(error='Unsupported attachment type. Use PDF, Office, image, CSV or TXT files.'),400
        upload.stream.seek(0,2)
        size=upload.stream.tell()
        upload.stream.seek(0)
        if size > MAX_UPLOAD_BYTES:
            return jsonify(error='Attachment must be 5 MB or smaller.'),400
        stored_name = uuid.uuid4().hex + '_' + attachment_name
        upload.save(UPLOAD_DIR / stored_name)
        stored_path = stored_name
    elif d.get('attachment'):
        attachment_name = str(d.get('attachment'))
        if len(attachment_name) > 255:
            return jsonify(error='Attachment name is too long.'),400

    execute('INSERT INTO service_requests(id,title,category,department,description,priority,required_date,attachment,contact,employee_id,status,created_at,updated_at,sla_deadline) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
      (rid,d['title'].strip(),d['category'],d['department'],d['description'].strip(),d['priority'],d.get('requiredDate') or None,attachment_name,d.get('contact'),g.user['id'],'Open',created,created,deadline))
    if stored_path:
        execute('INSERT INTO request_attachments(request_id,file_name,file_path,uploaded_by,uploaded_at) VALUES(%s,%s,%s,%s,%s)',
                (rid,attachment_name,stored_path,g.user['id'],created))
    execute('INSERT INTO request_history(request_id,status,user_id,note,created_at) VALUES(%s,%s,%s,%s,%s)',(rid,'Created',g.user['id'],'Request created',created))
    execute('INSERT INTO sla_records(request_id,priority,target_hours,started_at,deadline,status) VALUES(%s,%s,%s,%s,%s,%s)',
            (rid,d['priority'],SLA_HOURS[d['priority']],created,deadline,'Active'))
    log_audit('Request Created',rid,f"{g.user['name']} created {rid}")
    r=one('SELECT * FROM service_requests WHERE id=%s',(rid,))
    warning={'message':f"A similar open request already exists: {similar['id']}",'requestId':similar['id']} if similar else None
    return jsonify(request=request_obj(r, g.user),duplicateWarning=warning),201

@app.put('/api/requests/<rid>')
@auth_required
def update_request(rid):
    r=one('SELECT * FROM service_requests WHERE id=%s',(rid,));
    if not r:return jsonify(error='Request not found.'),404
    clause,params=scope_clause(g.user)
    if not one('SELECT 1 FROM service_requests WHERE id=%s AND '+clause,(rid,*params)):
        return jsonify(error='You are not allowed to update this request.'),403
    d=request.get_json(silent=True) or {}; allowed={'title':'title','description':'description','priority':'priority','requiredDate':'required_date','attachment':'attachment','contact':'contact'}
    sets=[]; vals=[]
    for k,col in allowed.items():
        if k in d: sets.append(f'{col}=%s'); vals.append(d[k])
    if not sets: return jsonify(request=request_obj(r, g.user))
    sets.append('updated_at=%s'); vals.append(now_utc()); vals.append(rid)
    execute('UPDATE service_requests SET '+','.join(sets)+' WHERE id=%s',vals); log_audit('Request Updated',rid,f"{g.user['name']} updated {rid}")
    return jsonify(request_obj(one('SELECT * FROM service_requests WHERE id=%s',(rid,)), g.user))

@app.put('/api/requests/<rid>/status')
@auth_required
@roles('executive','manager','admin')
def update_status(rid):
    r=one('SELECT * FROM service_requests WHERE id=%s',(rid,))
    if not r:return jsonify(error='Request not found.'),404
    if g.user['role']=='executive' and (r['department'] != g.user['department'] or (r['assigned_to'] and r['assigned_to'] != g.user['id'])):
        return jsonify(error='Executives can update only requests assigned to them in their department.'),403
    if g.user['role']=='manager' and r['department'] != g.user['department']:
        return jsonify(error='Managers can update only requests in their department.'),403
    d=request.get_json(silent=True) or {}; nxt=d.get('status'); allowed=TRANSITIONS.get(r['status'],[])
    if not nxt or nxt not in allowed:return jsonify(error=f'Cannot move request from "{r["status"]}" to "{nxt}" directly.'),400
    t=now_utc(); resolved=t if nxt=='Resolved' else r['resolved_at']
    execute('UPDATE service_requests SET status=%s,updated_at=%s,resolved_at=%s WHERE id=%s',(nxt,t,resolved,rid))
    execute('INSERT INTO request_history(request_id,status,user_id,note,created_at) VALUES(%s,%s,%s,%s,%s)',(rid,nxt,g.user['id'],d.get('note',''),t))
    if nxt=='Resolved':
        execute("UPDATE sla_records SET completed_at=%s,status=CASE WHEN %s<=deadline THEN 'Completed' ELSE 'Breached' END WHERE request_id=%s AND status='Active'",(t,t,rid))
    notify(r['employee_id'],f'{rid} status changed to {nxt}.',rid)
    log_audit('Status Changed',rid,f"{g.user['name']} set {rid} to {nxt}")
    return jsonify(request_obj(one('SELECT * FROM service_requests WHERE id=%s',(rid,)), g.user))

@app.post('/api/requests/<rid>/reopen')
@auth_required
def reopen(rid):
    r=one('SELECT * FROM service_requests WHERE id=%s',(rid,));
    if not r:return jsonify(error='Request not found.'),404
    if r['status'] not in ('Resolved','Closed'):return jsonify(error='Only Resolved or Closed requests can be reopened.'),400
    clause,params=scope_clause(g.user)
    if not one('SELECT 1 FROM service_requests WHERE id=%s AND '+clause,(rid,*params)):
        return jsonify(error='You are not allowed to reopen this request.'),403
    t=now_utc(); reason=(request.get_json(silent=True) or {}).get('reason','Reopened by user')
    execute('UPDATE service_requests SET status="In Progress",resolved_at=NULL,updated_at=%s WHERE id=%s',(t,rid))
    execute("UPDATE sla_records SET completed_at=NULL,status='Active',started_at=%s WHERE request_id=%s",(t,rid))
    execute('INSERT INTO request_history(request_id,status,user_id,note,created_at) VALUES(%s,%s,%s,%s,%s)',(rid,'Reopened -> In Progress',g.user['id'],reason,t))
    notify(r['assigned_to'] or r['employee_id'],f'{rid} has been reopened.',rid); log_audit('Request Reopened',rid,f"{g.user['name']} reopened {rid}")
    return jsonify(request_obj(one('SELECT * FROM service_requests WHERE id=%s',(rid,)), g.user))

@app.put('/api/requests/<rid>/assign')
@auth_required
@roles('manager','admin')
def assign(rid):
    r=one('SELECT * FROM service_requests WHERE id=%s',(rid,))
    d=request.get_json(silent=True) or {}
    assignee=one('SELECT id,name,role,department FROM users WHERE id=%s AND active=1',(d.get('assignedTo'),))
    if not r:return jsonify(error='Request not found.'),404
    if g.user['role']=='manager' and r['department'] != g.user['department']:
        return jsonify(error='Managers can assign only requests in their department.'),403
    if not assignee or assignee['role']!='executive' or assignee['department'] != r['department']:
        return jsonify(error='The assignee must be an active executive from the request department.'),400
    t=now_utc(); status='Assigned' if r['status']=='Open' else r['status']
    execute('UPDATE service_requests SET assigned_to=%s,status=%s,updated_at=%s WHERE id=%s',(assignee['id'],status,t,rid))
    execute('INSERT INTO request_assignments(request_id,assigned_to,assigned_by,assigned_at,note) VALUES(%s,%s,%s,%s,%s)',
            (rid,assignee['id'],g.user['id'],t,d.get('note','')))
    execute('INSERT INTO request_history(request_id,status,user_id,note,created_at) VALUES(%s,%s,%s,%s,%s)',(rid,f'Assigned to {assignee["name"]}',g.user['id'],d.get('note',''),t))
    notify(assignee['id'],f'{rid} has been assigned to you.',rid); notify(r['employee_id'],f'{rid} has been assigned to the {r["department"]} department.',rid)
    log_audit('Request Assigned',rid,f"{g.user['name']} assigned {rid} to {assignee['name']}")
    return jsonify(request_obj(one('SELECT * FROM service_requests WHERE id=%s',(rid,)), g.user))

@app.post('/api/requests/<rid>/comments')
@auth_required
def comment(rid):
    r=one('SELECT * FROM service_requests WHERE id=%s',(rid,)); d=request.get_json(silent=True) or {}; text=d.get('text','').strip()
    if not r:return jsonify(error='Request not found.'),404
    clause,params=scope_clause(g.user)
    if not one('SELECT 1 FROM service_requests WHERE id=%s AND '+clause,(rid,*params)):
        return jsonify(error='You cannot comment on this request.'),403
    if not text:return jsonify(error='Comment text is required.'),400
    if len(text)>3000:return jsonify(error='Comment must be 3000 characters or fewer.'),400
    if d.get('internal') and g.user['role']=='employee':return jsonify(error='Employees cannot post internal notes.'),403
    cid='CMT-'+uuid.uuid4().hex[:20]; t=now_utc()
    execute('INSERT INTO request_comments(id,request_id,user_id,user_name,role,text,internal,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(cid,rid,g.user['id'],g.user['name'],g.user['role'],text,bool(d.get('internal')),t))
    execute('UPDATE service_requests SET updated_at=%s WHERE id=%s',(t,rid)); log_audit('Comment Added',rid,f"{g.user['name']} commented on {rid}")
    return jsonify(request_obj(one('SELECT * FROM service_requests WHERE id=%s',(rid,)), g.user)),201

@app.get('/api/dashboard/employee')
@auth_required
def employee_dashboard():
    rs=rows('SELECT * FROM service_requests WHERE employee_id=%s',(g.user['id'],)); counts={}
    for r in rs: counts[r['status']]=counts.get(r['status'],0)+1
    rs.sort(key=lambda x:x['updated_at'],reverse=True)
    return jsonify(counts=counts,recent=[request_obj(x, g.user) for x in rs[:5]])

@app.get('/api/dashboard/manager')
@auth_required
@roles('manager','admin')
def manager_dashboard(): return dashboard_data()

@app.get('/api/dashboard/admin')
@auth_required
@roles('admin')
def admin_dashboard(): return dashboard_data()

def dashboard_data():
    clause,params=scope_clause(g.user); rs=rows('SELECT * FROM service_requests WHERE '+clause,params); counts={}
    for r in rs: counts[r['status']]=counts.get(r['status'],0)+1
    critical=sum(r['priority']=='Critical' and r['status'] not in ('Resolved','Closed') for r in rs)
    breaches=sum(sla_state({'slaDeadline':r['sla_deadline'],'status':r['status'],'resolvedAt':r['resolved_at']}) in ('SLA_BREACHED','SLA_BREACHED_ON_CLOSE') for r in rs)
    resolved=[r for r in rs if r['resolved_at']]; avg=round(sum((r['resolved_at']-r['created_at']).total_seconds()/3600 for r in resolved)/len(resolved)) if resolved else 0
    def group(field):
        out={}
        for r in rs: out[r[field]]=out.get(r[field],0)+1
        return out
    ids=sorted({r['assigned_to'] for r in rs if r['assigned_to']}); workload=[]
    for uid in ids:
        u=one('SELECT name FROM users WHERE id=%s',(uid,)); workload.append({'userId':uid,'name':u['name'] if u else uid,'openCount':sum(r['assigned_to']==uid and r['status'] not in ('Resolved','Closed') for r in rs)})
    return jsonify(kpis={'totalRequests':len(rs),'openRequests':counts.get('Open',0),'criticalRequests':critical,'slaBreaches':breaches,'avgResolutionHours':avg,'pendingRequests':counts.get('Pending Information',0)+counts.get('Open',0)},charts={'byCategory':group('category'),'byPriority':group('priority'),'byStatus':group('status'),'byDepartment':group('department')},workload=workload)

@app.get('/api/attachments/<int:aid>')
@auth_required
def download_attachment(aid):
    a=one('SELECT ra.file_name,ra.file_path,s.employee_id,s.department, s.assigned_to FROM request_attachments ra JOIN service_requests s ON s.id=ra.request_id WHERE ra.id=%s',(aid,))
    if not a:return jsonify(error='Attachment not found.'),404
    clause,params=scope_clause(g.user)
    if not one('SELECT 1 FROM service_requests WHERE id=(SELECT request_id FROM request_attachments WHERE id=%s) AND '+clause,(aid,*params)):
        return jsonify(error='You cannot access this attachment.'),403
    safe_path=Path(a['file_path']).name
    return send_from_directory(UPLOAD_DIR,safe_path,as_attachment=True,download_name=a['file_name'])

@app.get('/api/notifications')
@auth_required
def notifications():
    ns=rows('SELECT id,user_id,message,request_id,is_read,created_at FROM notifications WHERE user_id=%s ORDER BY created_at DESC',(g.user['id'],))
    return jsonify([{'id':n['id'],'userId':n['user_id'],'message':n['message'],'requestId':n['request_id'],'read':bool(n['is_read']),'createdAt':iso(n['created_at'])} for n in ns])

@app.put('/api/notifications/<nid>/read')
@auth_required
def notification_read(nid):
    n=one('SELECT * FROM notifications WHERE id=%s AND user_id=%s',(nid,g.user['id']))
    if not n:return jsonify(error='Notification not found.'),404
    execute('UPDATE notifications SET is_read=1 WHERE id=%s',(nid,)); n['is_read']=1
    return jsonify(id=nid,userId=g.user['id'],message=n['message'],requestId=n['request_id'],read=True,createdAt=iso(n['created_at']))

@app.get('/api/meta/departments')
@auth_required
def meta_departments(): return jsonify(rows('SELECT id,name,manager_id AS managerId FROM departments ORDER BY name'))

@app.get('/api/meta/categories')
@auth_required
def meta_categories(): return jsonify(rows('SELECT id,name,department,default_priority AS defaultPriority FROM categories ORDER BY name'))

@app.get('/api/meta/users')
@auth_required
def meta_users(): return jsonify(rows('SELECT id,name,email,role,department,active FROM users WHERE active=1 ORDER BY name'))

@app.get('/api/admin/users')
@auth_required
@roles('admin')
def admin_users(): return jsonify(rows('SELECT id,name,email,role,department,active,created_at AS createdAt FROM users ORDER BY name'))

@app.post('/api/admin/users')
@auth_required
@roles('admin')
def admin_create_user():
    d=request.get_json(silent=True) or {}
    if not all(d.get(x) for x in ('name','email','role','password')):return jsonify(error='name, email, role and password are required.'),400
    if one('SELECT id FROM users WHERE LOWER(email)=LOWER(%s)',(d['email'],)):return jsonify(error='A user with this email already exists.'),409
    uid='U-'+str(1000+one('SELECT COUNT(*) n FROM users')['n']+1)
    execute('INSERT INTO users(id,name,email,password_hash,role,department,active) VALUES(%s,%s,%s,%s,%s,%s,1)',(uid,d['name'],d['email'],generate_password_hash(d['password']),d['role'],d.get('department'))); log_audit('User Created',None,f"{g.user['name']} created user {uid}")
    return jsonify(id=uid,name=d['name'],email=d['email'],role=d['role'],department=d.get('department'),active=True),201

@app.put('/api/admin/users/<uid>')
@auth_required
@roles('admin')
def admin_update_user(uid):
    d=request.get_json(silent=True) or {}; sets=[]; vals=[]
    for k in ('name','role','department','active'):
        if k in d: sets.append(f'{k}=%s'); vals.append(d[k])
    if not sets:return jsonify(error='No changes supplied.'),400
    vals.append(uid); execute('UPDATE users SET '+','.join(sets)+' WHERE id=%s',vals)
    u=one('SELECT id,name,email,role,department,active FROM users WHERE id=%s',(uid,));
    if not u:return jsonify(error='User not found.'),404
    log_audit('User Updated',None,f"{g.user['name']} updated {uid}"); return jsonify(u)

@app.get('/api/admin/departments')
@auth_required
@roles('admin')
def admin_departments(): return meta_departments()

@app.post('/api/admin/departments')
@auth_required
@roles('admin')
def admin_create_department():
    d=request.get_json(silent=True) or {}
    if not d.get('name'):return jsonify(error='name is required.'),400
    if one('SELECT id FROM departments WHERE LOWER(name)=LOWER(%s)',(d['name'].strip(),)): return jsonify(error='A department with this name already exists.'),409
    did='D-'+str(one("SELECT COALESCE(MAX(CAST(SUBSTRING(id,3) AS UNSIGNED)),0) n FROM departments")['n']+1); execute('INSERT INTO departments(id,name,manager_id) VALUES(%s,%s,%s)',(did,d['name'].strip(),d.get('managerId'))); log_audit('Department Created',None,f"{g.user['name']} created department {d['name']}"); return jsonify(id=did,name=d['name'],managerId=d.get('managerId')),201

@app.put('/api/admin/departments/<did>')
@auth_required
@roles('admin')
def admin_update_department(did):
    d=request.get_json(silent=True) or {}; sets=[]; vals=[]
    if 'name' in d:sets.append('name=%s');vals.append(d['name'])
    if 'managerId' in d:sets.append('manager_id=%s');vals.append(d['managerId'])
    vals.append(did);execute('UPDATE departments SET '+','.join(sets)+' WHERE id=%s',vals); return jsonify(one('SELECT id,name,manager_id AS managerId FROM departments WHERE id=%s',(did,)))

@app.get('/api/admin/categories')
@auth_required
@roles('admin')
def admin_categories(): return meta_categories()

@app.post('/api/admin/categories')
@auth_required
@roles('admin')
def admin_create_category():
    d=request.get_json(silent=True) or {}
    if not d.get('name') or not d.get('department'):return jsonify(error='name and department are required.'),400
    if d.get('defaultPriority','Medium') not in SLA_HOURS: return jsonify(error='Invalid default priority.'),400
    if one('SELECT id FROM categories WHERE LOWER(name)=LOWER(%s)',(d['name'].strip(),)): return jsonify(error='A category with this name already exists.'),409
    cid='C-'+str(one("SELECT COALESCE(MAX(CAST(SUBSTRING(id,3) AS UNSIGNED)),0) n FROM categories")['n']+1); execute('INSERT INTO categories(id,name,department,default_priority) VALUES(%s,%s,%s,%s)',(cid,d['name'].strip(),d['department'],d.get('defaultPriority','Medium'))); log_audit('Category Created',None,f"{g.user['name']} created category {d['name']}"); return jsonify(id=cid,name=d['name'],department=d['department'],defaultPriority=d.get('defaultPriority','Medium')),201

@app.get('/api/admin/audit-logs')
@auth_required
@roles('admin')
def admin_audit():
    logs=rows('SELECT id,user_id AS userId,action,request_id AS requestId,details,created_at AS timestamp FROM audit_logs ORDER BY created_at DESC LIMIT 200');
    for x in logs:x['timestamp']=iso(x['timestamp'])
    return jsonify(logs)

@app.route('/', defaults={'path':''})
@app.route('/<path:path>')
def frontend(path):
    target=FRONTEND_DIR/path if path else FRONTEND_DIR/'index.html'
    if target.exists() and target.is_file(): return send_from_directory(FRONTEND_DIR,path or 'index.html')
    return send_from_directory(FRONTEND_DIR,'index.html')

@app.errorhandler(Exception)
def handle_error(e):
    app.logger.exception(e)

    if isinstance(e, Error):
        return jsonify(
            error='Database error',
            details=str(e)
        ), 500

    return jsonify(
        error='Internal server error',
        details=str(e)
    ), 500
if __name__=='__main__':
    app.run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=True)
