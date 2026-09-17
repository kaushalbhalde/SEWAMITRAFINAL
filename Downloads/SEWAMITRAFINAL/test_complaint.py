import urllib.request, urllib.parse, http.cookiejar, json

BASE = 'http://127.0.0.1:5000'

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# Login
login = {'email':'customer@bridge.local','password':'demo123'}
req = urllib.request.Request(BASE + '/api/auth/login', data=json.dumps(login).encode('utf-8'), headers={'Content-Type':'application/json'})
try:
    res = opener.open(req)
    print('Login response:', res.read().decode())
except Exception as e:
    print('Login failed:', e)
    import sys; sys.exit(1)

# Create complaint
complaint = {'subject':'Automated test complaint','description':'Complaint created by automated test script','job_id':None}
req2 = urllib.request.Request(BASE + '/api/complaints', data=json.dumps(complaint).encode('utf-8'), headers={'Content-Type':'application/json'})
try:
    res2 = opener.open(req2)
    print('Create complaint response:', res2.read().decode())
except Exception as e:
    print('Create failed:', e)
    import sys; sys.exit(1)

# List complaints
req3 = urllib.request.Request(BASE + '/api/complaints')
try:
    res3 = opener.open(req3)
    print('List complaints:', res3.read().decode())
except Exception as e:
    print('List failed:', e)
