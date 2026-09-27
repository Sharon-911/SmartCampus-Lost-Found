import os,secrets
from datetime import datetime,date,timedelta
from functools import wraps
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask,render_template,request,redirect,url_for,flash,session,abort
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.utils import secure_filename
from ml.matcher import score
load_dotenv(); BASE=Path(__file__).resolve().parent
app=Flask(__name__,instance_relative_config=True); app.config.update(SECRET_KEY=os.getenv('SECRET_KEY','dev-change'),SQLALCHEMY_DATABASE_URI='sqlite:///'+str(BASE/'instance/smartcampus.db'),SQLALCHEMY_TRACK_MODIFICATIONS=False,MAX_CONTENT_LENGTH=4*1024*1024,COLLEGE_EMAIL_DOMAIN=os.getenv('COLLEGE_EMAIL_DOMAIN','college.edu').lower().lstrip('@'),ADMIN_EMAIL=os.getenv('ADMIN_EMAIL','admin@college.edu'),ADMIN_PASSWORD=os.getenv('ADMIN_PASSWORD','Admin@123'),UPLOAD_FOLDER=str(BASE/'static/uploads'))
db=SQLAlchemy(app); csrf=CSRFProtect(app); limiter=Limiter(key_func=get_remote_address,app=app,default_limits=['200 per day','60 per hour']); Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True,exist_ok=True)
class User(db.Model):
 id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(120),nullable=False); email=db.Column(db.String(180),unique=True,nullable=False); register_number=db.Column(db.String(60),unique=True,nullable=False); department=db.Column(db.String(100)); year=db.Column(db.String(30)); password_hash=db.Column(db.String(255),nullable=False); role=db.Column(db.String(20),default='STUDENT'); created_at=db.Column(db.DateTime,default=datetime.utcnow)
class Report(db.Model):
 id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False); type=db.Column(db.String(10),nullable=False); category=db.Column(db.String(80),nullable=False); item_name=db.Column(db.String(150),nullable=False); description=db.Column(db.Text,nullable=False); brand=db.Column(db.String(100),default=''); colour=db.Column(db.String(80),default=''); location=db.Column(db.String(180),nullable=False); date=db.Column(db.Date,nullable=False); time=db.Column(db.String(40),nullable=False); image_path=db.Column(db.String(255)); status=db.Column(db.String(20),default='ACTIVE'); is_flagged=db.Column(db.Boolean,default=False); created_at=db.Column(db.DateTime,default=datetime.utcnow); user=db.relationship('User',backref='reports')
class PrivateDetail(db.Model):
 id=db.Column(db.Integer,primary_key=True); report_id=db.Column(db.Integer,db.ForeignKey('report.id'),unique=True,nullable=False); private_information=db.Column(db.Text,nullable=False); report=db.relationship('Report',backref=db.backref('private_detail',uselist=False))
class Match(db.Model):
 id=db.Column(db.Integer,primary_key=True); lost_report_id=db.Column(db.Integer,db.ForeignKey('report.id')); found_report_id=db.Column(db.Integer,db.ForeignKey('report.id')); text_score=db.Column(db.Float); location_score=db.Column(db.Float); time_score=db.Column(db.Float); category_score=db.Column(db.Float); overall_score=db.Column(db.Float); status=db.Column(db.String(30),default='POTENTIAL'); created_at=db.Column(db.DateTime,default=datetime.utcnow); lost_report=db.relationship('Report',foreign_keys=[lost_report_id]); found_report=db.relationship('Report',foreign_keys=[found_report_id])
class Claim(db.Model):
 id=db.Column(db.Integer,primary_key=True); match_id=db.Column(db.Integer,db.ForeignKey('match.id')); claimant_id=db.Column(db.Integer,db.ForeignKey('user.id')); answers=db.Column(db.Text); status=db.Column(db.String(30),default='PENDING'); admin_comment=db.Column(db.Text,default=''); reviewed_at=db.Column(db.DateTime); match=db.relationship('Match',backref='claims'); claimant=db.relationship('User')
class Notification(db.Model):
 id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id')); message=db.Column(db.String(500)); is_read=db.Column(db.Boolean,default=False); created_at=db.Column(db.DateTime,default=datetime.utcnow); user=db.relationship('User',backref='notifications')
def me(): return db.session.get(User,session.get('user_id')) if session.get('user_id') else None
@app.context_processor
def ctx():
 u=me(); return {'current_user':u,'unread_notifications':Notification.query.filter_by(user_id=u.id,is_read=False).count() if u else 0}
def login_required(f):
 @wraps(f)
 def w(*a,**k):
  if not me(): flash('Please log in to continue.','warning'); return redirect(url_for('login'))
  return f(*a,**k)
 return w
def admin_required(f):
 @wraps(f)
 def w(*a,**k):
  if not me() or me().role!='ADMIN': abort(403)
  return f(*a,**k)
 return w
def notify(uid,msg): db.session.add(Notification(user_id=uid,message=msg))
def valid_image(n): return '.' in n and n.rsplit('.',1)[1].lower() in {'jpg','jpeg','png','webp'}
def run_matches(lost=None,found=None):
 losts=[lost] if lost else Report.query.filter_by(type='LOST').filter(Report.status.in_(['ACTIVE','APPROVED'])).all(); founds=[found] if found else Report.query.filter_by(type='FOUND',status='APPROVED').all()
 for l in losts:
  for f in founds:
   if l.id==f.id or Match.query.filter_by(lost_report_id=l.id,found_report_id=f.id).first(): continue
   s=score(l,f)
   if s['overall']>=35:
    db.session.add(Match(lost_report_id=l.id,found_report_id=f.id,text_score=s['text'],location_score=s['location'],time_score=s['time'],category_score=s['category'],overall_score=s['overall']))
    notify(l.user_id,f"Potential match found for '{l.item_name}' — {s['overall']:.0f}% similarity.")
@app.route('/')
def index(): return render_template('index.html')
@app.route('/register',methods=['GET','POST'])
def register():
 if request.method=='POST':
  f=request.form; email=f.get('email','').strip().lower(); reg=f.get('register_number','').strip(); pw=f.get('password','')
  if not all(f.get(x,'').strip() for x in ['name','email','register_number','department','year','password','confirm_password']): flash('Please complete every required field.','danger')
  elif not email.endswith('@'+app.config['COLLEGE_EMAIL_DOMAIN']): flash('Use your valid college email domain.','danger')
  elif len(pw)<8 or pw!=f.get('confirm_password'): flash('Check password length and confirmation.','danger')
  elif User.query.filter((User.email==email)|(User.register_number==reg)).first(): flash('Email or register number is already registered.','danger')
  else:
   db.session.add(User(name=f['name'].strip(),email=email,register_number=reg,department=f['department'].strip(),year=f['year'],password_hash=generate_password_hash(pw))); db.session.commit(); flash('Registration successful.','success'); return redirect(url_for('login'))
 return render_template('register.html')
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  u=User.query.filter_by(email=request.form.get('email','').strip().lower()).first()
  if u and check_password_hash(u.password_hash,request.form.get('password','')): session.clear();session['user_id']=u.id;return redirect(url_for('admin_dashboard' if u.role=='ADMIN' else 'dashboard'))
  flash('Invalid email or password.','danger')
 return render_template('login.html')
@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('index'))
@app.route('/dashboard')
@login_required
def dashboard():
 u=me(); return render_template('dashboard.html',lost=Report.query.filter_by(user_id=u.id,type='LOST').filter(Report.status!='RETURNED').count(),found=Report.query.filter_by(user_id=u.id,type='FOUND').filter(Report.status!='RETURNED').count(),matches=Match.query.join(Report,Match.lost_report_id==Report.id).filter(Report.user_id==u.id).count(),claims=Claim.query.filter_by(claimant_id=u.id).filter(Claim.status.in_(['PENDING','UNDER REVIEW'])).count(),returned=Report.query.filter_by(user_id=u.id,status='RETURNED').count(),recent=Notification.query.filter_by(user_id=u.id).order_by(Notification.created_at.desc()).limit(5).all())
@app.route('/report/<rtype>',methods=['GET','POST'])
@login_required
def report_item(rtype):
 if rtype not in ['lost','found']: abort(404)
 u=me(); typ=rtype.upper()
 if request.method=='POST':
  f=request.form; vals=[f.get(x,'').strip() for x in ['category','item_name','description','location','date','time','private_information']]
  if not all(vals) or len(vals[2])<12: flash('Complete the required fields and provide a meaningful description.','danger'); return render_template('report_form.html',rtype=rtype)
  try: d=date.fromisoformat(f['date'])
  except: flash('Invalid date.','danger'); return render_template('report_form.html',rtype=rtype)
  if Report.query.filter_by(user_id=u.id,type=typ).filter(Report.created_at>=datetime.utcnow()-timedelta(days=1)).count()>=3: flash('Daily report limit reached.','danger'); return render_template('report_form.html',rtype=rtype)
  img=request.files.get('image'); path=None
  if img and img.filename:
   if not valid_image(img.filename): flash('Only JPG, JPEG, PNG and WEBP images are allowed.','danger'); return render_template('report_form.html',rtype=rtype)
   ext=img.filename.rsplit('.',1)[1].lower(); name=secure_filename(secrets.token_hex(12)+'.'+ext); img.save(Path(app.config['UPLOAD_FOLDER'])/name); path='uploads/'+name
  r=Report(user_id=u.id,type=typ,category=f['category'].strip(),item_name=f['item_name'].strip(),description=f['description'].strip(),brand=f.get('brand','').strip(),colour=f.get('colour','').strip(),location=f['location'].strip(),date=d,time=f['time'].strip(),image_path=path,status='PENDING' if typ=='FOUND' else 'ACTIVE'); db.session.add(r); db.session.flush(); db.session.add(PrivateDetail(report_id=r.id,private_information=f['private_information'].strip())); notify(u.id,f'Your {rtype} report was submitted as {r.status}.'); db.session.commit()
  if typ=='LOST': run_matches(lost=r); db.session.commit()
  flash('Report submitted successfully.','success'); return redirect(url_for('my_reports'))
 return render_template('report_form.html',rtype=rtype)
@app.route('/reports')
@login_required
def my_reports(): return render_template('my_reports.html',reports=Report.query.filter_by(user_id=me().id).order_by(Report.created_at.desc()).all())
@app.route('/search')
@login_required
def search():
 q=request.args.get('q','').strip(); typ=request.args.get('type',''); cat=request.args.get('category',''); loc=request.args.get('location','').strip(); brand=request.args.get('brand','').strip(); x=Report.query.filter(Report.status.in_(['ACTIVE','APPROVED']))
 if q:x=x.filter((Report.item_name.ilike('%'+q+'%'))|(Report.description.ilike('%'+q+'%')))
 if typ in ['LOST','FOUND']:x=x.filter_by(type=typ)
 if cat:x=x.filter_by(category=cat)
 if loc:x=x.filter(Report.location.ilike('%'+loc+'%'))
 if brand:x=x.filter(Report.brand.ilike('%'+brand+'%'))
 return render_template('search.html',reports=x.order_by(Report.created_at.desc()).all())
@app.route('/report/<int:rid>')
@login_required
def report_detail(rid):
 r=db.session.get(Report,rid) or abort(404); return render_template('report_details.html',report=r)
@app.route('/matches')
@login_required
def matches(): return render_template('matches.html',matches=Match.query.join(Report,Match.lost_report_id==Report.id).filter(Report.user_id==me().id).order_by(Match.overall_score.desc()).all())
@app.route('/claim/<int:mid>',methods=['GET','POST'])
@login_required
def claim(mid):
 m=db.session.get(Match,mid) or abort(404)
 if m.lost_report.user_id!=me().id: abort(403)
 if request.method=='POST':
  ans=request.form.get('answers','').strip()
  if len(ans)<20: flash('Please provide more verification detail.','danger')
  else: db.session.add(Claim(match_id=mid,claimant_id=me().id,answers=ans));notify(me().id,'Your ownership claim was submitted for admin review.');db.session.commit();flash('Claim submitted.','success');return redirect(url_for('matches'))
 return render_template('claim.html',match=m)
@app.route('/notifications')
@login_required
def notifications():
 ns=Notification.query.filter_by(user_id=me().id).order_by(Notification.created_at.desc()).all()
 for n in ns:n.is_read=True
 db.session.commit();return render_template('notifications.html',notifications=ns)
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
 stats={k:Report.query.filter_by(status=v).count() for k,v in [('pending','PENDING'),('approved','APPROVED'),('rejected','REJECTED'),('returned','RETURNED')]};stats.update(matches=Match.query.count(),claims=Claim.query.filter(Claim.status.in_(['PENDING','UNDER REVIEW'])).count(),flagged=Report.query.filter_by(is_flagged=True).count());return render_template('admin/dashboard.html',stats=stats,categories=db.session.query(Report.category,db.func.count(Report.id)).group_by(Report.category).all())
@app.route('/admin/reports')
@admin_required
def admin_reports():
 q=Report.query.order_by(Report.created_at.desc());s=request.args.get('status','');
 if s:q=q.filter_by(status=s)
 return render_template('admin/reports.html',reports=q.all())
@app.route('/admin/reports/<int:rid>/<action>',methods=['POST'])
@admin_required
def admin_report_action(rid,action):
 r=db.session.get(Report,rid) or abort(404)
 if action=='approve' and r.type=='FOUND':r.status='APPROVED';notify(r.user_id,'Your found report was approved.');run_matches(found=r)
 elif action=='reject':r.status='REJECTED';notify(r.user_id,'Your report was rejected by an administrator.')
 elif action=='flag':r.is_flagged=True
 elif action=='unflag':r.is_flagged=False
 else: abort(400)
 db.session.commit();return redirect(url_for('admin_reports'))
@app.route('/admin/matches')
@admin_required
def admin_matches(): return render_template('admin/matches.html',matches=Match.query.order_by(Match.overall_score.desc()).all())
@app.route('/admin/claims')
@admin_required
def admin_claims(): return render_template('admin/claims.html',claims=Claim.query.order_by(Claim.id.desc()).all())
@app.route('/admin/claims/<int:cid>/<action>',methods=['POST'])
@admin_required
def admin_claim_action(cid,action):
 c=db.session.get(Claim,cid) or abort(404)
 if action=='approve':c.status='APPROVED';c.match.status='CLAIM_APPROVED';notify(c.claimant_id,'Your ownership claim was approved.')
 elif action=='reject':c.status='REJECTED';c.match.status='CLAIM_REJECTED';notify(c.claimant_id,'Your ownership claim was rejected after review.')
 elif action=='info':c.status='UNDER REVIEW';notify(c.claimant_id,'The administrator requested more information.')
 else:abort(400)
 c.admin_comment=request.form.get('comment','');c.reviewed_at=datetime.utcnow();db.session.commit();return redirect(url_for('admin_claims'))
@app.route('/admin/return/<int:rid>',methods=['POST'])
@admin_required
def mark_returned(rid):
 r=db.session.get(Report,rid) or abort(404);r.status='RETURNED';notify(r.user_id,f"'{r.item_name}' has been marked as returned successfully.");db.session.commit();return redirect(url_for('admin_claims'))
@app.errorhandler(403)
def e403(e):return render_template('error.html',code=403,message='You do not have permission to access this page.'),403
@app.errorhandler(404)
def e404(e):return render_template('error.html',code=404,message='The page you requested could not be found.'),404
with app.app_context():
 db.create_all()
 if not User.query.filter_by(email=app.config['ADMIN_EMAIL']).first():
  db.session.add(User(name='SmartCampus Admin',email=app.config['ADMIN_EMAIL'],register_number='ADMIN-001',department='Administration',year='Staff',password_hash=generate_password_hash(app.config['ADMIN_PASSWORD']),role='ADMIN'));db.session.commit()
if __name__=='__main__':app.run(debug=True)
