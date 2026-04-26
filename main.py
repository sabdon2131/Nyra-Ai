import os
import re
import ast
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# =====================================================
# CONFIG
# =====================================================
class Config:
    def __init__(self):
        self.settings = {
            "safe_code_gate": True,
            "max_iterations": 10,
            "retry_on_failure": True,
            "replan_if_blocked": True,
            "completion_check": True
        }

    def get(self,key,default=None):
        return self.settings.get(key,default)

config = Config()

# =====================================================
# MEMORY
# =====================================================
class Memory:
    def __init__(self):
        self.context_chunks=[]

    def add_context(self,text):
        self.context_chunks.append(text)

    def retrieve(self,query):
        return "\n".join(self.context_chunks[-3:])

memory = Memory()

# =====================================================
# MODEL PROVIDER
# =====================================================
class Provider:
    def __init__(self):
        self.url="https://openrouter.ai/api/v1/chat/completions"
        self.model="mistralai/mixtral-8x7b-instruct"

    def generate(self,prompt,system="You are NYRA"):
        key=os.environ.get("OPENROUTER_API_KEY","")
        if not key:
            return "OPENROUTER_API_KEY missing"
        try:
            r=requests.post(
                self.url,
                headers={
                    "Authorization":f"Bearer {key}",
                    "Content-Type":"application/json"
                },
                json={
                    "model":self.model,
                    "messages":[
                        {"role":"system","content":system},
                        {"role":"user","content":prompt}
                    ]
                },
                timeout=25
            )
            data=r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Provider error: {e}"

provider=Provider()

# =====================================================
# LIGHTWEIGHT ARBITRATION
# =====================================================
def lightweight_provider_compare(a,b):
    return a if len(a)>=len(b) else b

# =====================================================
# SAFETY GATE
# =====================================================
class SystemGuard:
    patterns=[r'os\\.system',r'eval\\(',r'exec\\(']

    @staticmethod
    def validate(code):
        try:
            ast.parse(code)
        except Exception as e:
            return {"safe":False,"issue":str(e)}
        for p in SystemGuard.patterns:
            if re.search(p,code,re.I):
                return {"safe":False,"issue":p}
        return {"safe":True}

def approval_gate(code):
    return SystemGuard.validate(code)

# =====================================================
# PLUGIN TOOLS
# =====================================================
class PluginTools:
    def __init__(self):
        self.registry={}

    def register(self,name,fn):
        self.registry[name]=fn

    def call(self,name,*a,**k):
        if name not in self.registry:
            return "tool not found"
        return self.registry[name](*a,**k)

tools=PluginTools()

def calculator(x,y):
    return x+y

tools.register("add",calculator)

# =====================================================
# TASK GRAPH
# =====================================================
class TaskGraphExecutor:
    def __init__(self):
        self.graph=[]

    def add(self,task,deps=None):
        self.graph.append({
            "task":task,
            "deps":deps or [],
            "status":"pending"
        })

    def run(self):
        for t in self.graph:
            t["status"]="done"
        return self.graph

# =====================================================
# JOB QUEUE
# =====================================================
JOB_QUEUE=[]

def submit_job(goal):
    jid=str(len(JOB_QUEUE)+1)
    JOB_QUEUE.append({
        "id":jid,
        "goal":goal,
        "status":"queued"
    })
    return jid

# =====================================================
# LONG-HORIZON GOAL ENGINE
# =====================================================
class GoalEngine:
    def __init__(self):
        self.policy={
            "max_iterations":config.get("max_iterations"),
            "retry_on_failure":config.get("retry_on_failure"),
            "replan_if_blocked":config.get("replan_if_blocked")
        }

    def run_goal_loop(self,goal):
        state={"goal":goal,"step":0,"complete":False}

        while (
            state["step"] < self.policy["max_iterations"]
            and not state["complete"]
        ):
            state["step"] += 1

            if state["step"] >= 3:
                state["complete"] = True

        return state

goal_engine=GoalEngine()

# =====================================================
# BRAIN BRIDGE
# =====================================================
class BrainBridge:
    def consensus_execute(self,prompt):
        a=provider.generate(prompt)
        b=provider.generate(prompt)
        merged=lightweight_provider_compare(a,b)
        arbiter_prompt=f"Verify and improve this answer:\n{merged}"
        return provider.generate(
            arbiter_prompt,
            system="You are consensus arbiter"
        )

# =====================================================
# ORCHESTRATOR
# =====================================================
class Orchestrator:
    def __init__(self):
        self.bridge=BrainBridge()

    def run_goal(self,goal):
        tg=TaskGraphExecutor()
        tg.add("plan")
        tg.add("build",["plan"])
        tg.add("verify",["build"])
        tasks=tg.run()

        if "build" in goal.lower() or "project" in goal.lower():
            return {
                "response":self.bridge.consensus_execute(goal),
                "tasks":tasks,
                "action":"assembled_project"
            }

        return {
            "response":provider.generate(
                f"Break this goal into subtasks: {goal}"
            ),
            "tasks":tasks,
            "action":"planned_goal"
        }

orch=Orchestrator()

# =====================================================
# SAFE CONFIG EVOLUTION
# =====================================================
class ConfigEvolution:
    def propose(self,proposal):
        return {
            "pending_approval":True,
            "proposal":proposal
        }

evolver=ConfigEvolution()

# =====================================================
# REQUEST ROUTING
# =====================================================
def process(text):
    t=text.lower()

    if any(k in t for k in ["build","architect","project"]):
        return orch.run_goal(text)

    if "learn rule" in t:
        return evolver.propose(text)

    context=memory.retrieve(text)

    out=provider.generate(
        text,
        system=f"Use context if relevant:\n{context}"
    )

    return {
        "response":out,
        "action":"chat"
    }

# =====================================================
# ROUTES
# =====================================================
@app.route('/')
def home():
    return jsonify({
        "status":"NYRA Final running"
    })

@app.route('/ask',methods=['POST'])
def ask():
    data=request.json or {}
    return jsonify(
        process(
            data.get('text','')
        )
    )

@app.route('/jobs')
def jobs():
    return jsonify(JOB_QUEUE)

@app.route('/submit_goal',methods=['POST'])
def submit_goal_route():
    goal=request.json.get('goal','')
    return jsonify({
        'job_id':submit_job(goal)
    })

@app.route('/run_goal',methods=['POST'])
def run_goal_route():
    goal=request.json.get('goal','')
    return jsonify(
        goal_engine.run_goal_loop(goal)
    )

@app.route('/tool_test')
def tool_test():
    return jsonify({
        'result':tools.call('add',2,3)
    })

@app.route('/ui')
def ui():
    return '''
<html>
<body style="background:#111;color:white;font-family:Arial;padding:20px;">
<h2>NYRA</h2>
<input id=i style="width:70%;padding:10px">
<button onclick="s()">Send</button>
<pre id=r></pre>
<script>
async function s(){
 let x=await fetch('/ask',{
 method:'POST',
 headers:{'Content-Type':'application/json'},
 body:JSON.stringify({text:i.value})
 });
 let d=await x.json();
 r.innerText=JSON.stringify(d,null,2)
}
</script>
</body>
</html>
'''

if __name__=='__main__':
    port=int(os.environ.get('PORT',10000))
    app.run(host='0.0.0.0',port=port)
