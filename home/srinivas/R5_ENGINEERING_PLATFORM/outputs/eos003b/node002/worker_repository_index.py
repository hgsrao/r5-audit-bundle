import json,time,hashlib
from pathlib import Path
root=Path.home()/"R5_ENGINEERING_PLATFORM"
started=time.perf_counter()
records=[]
for folder in [root/"bridge/src",root/"bridge/tests",root/"architecture"]:
    for p in sorted(folder.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            records.append({"path":str(p.relative_to(root)),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
result={"node":"NODE-002","task":"engineering platform repository index","status":"PASS","file_count":len(records),"duration_seconds":time.perf_counter()-started,"files":records,"R5_production_accessed":False}
(root/"outputs/eos003b/repository_index.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k!="files"}))
