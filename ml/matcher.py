import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

WEIGHTS={'text':.50,'location':.20,'time':.15,'category':.15}
def norm(s): return re.sub(r'\s+',' ',(s or '').lower().strip())
def text_similarity(a,b):
    x=' '.join([a.item_name,a.description,a.brand,a.colour]); y=' '.join([b.item_name,b.description,b.brand,b.colour])
    if not x.strip() or not y.strip(): return 0.0
    v=TfidfVectorizer(stop_words='english').fit_transform([norm(x),norm(y)])
    return float(cosine_similarity(v[0:1],v[1:2])[0][0]*100)
def location_similarity(a,b):
    x,y=set(norm(a.location).split()),set(norm(b.location).split())
    return 100.0 if x==y and x else round(len(x&y)/max(1,len(x|y))*100,2)
def time_similarity(a,b):
    if not a.date or not b.date:return 0.0
    return max(0.0,100.0-min(abs((b.date-a.date).days),30)*100/30)
def category_similarity(a,b): return 100.0 if norm(a.category)==norm(b.category) else 0.0
def score(a,b):
    s={'text':text_similarity(a,b),'location':location_similarity(a,b),'time':time_similarity(a,b),'category':category_similarity(a,b)}
    s['overall']=sum(WEIGHTS[k]*s[k] for k in WEIGHTS)
    return {k:round(v,2) for k,v in s.items()}
