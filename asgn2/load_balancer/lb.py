from flask import Flask, request, json, jsonify
from consistent_hashing import consistentHash
from threading import Lock, Semaphore
import random, logging, requests, os, time

app = Flask(__name__)
app.config['DEBUG'] = True
# log = logging.getLogger('werkzeug')
# log.disabled = True

num_replicas = 3

# mapper = consistentHash(num_servers = 2, num_slots = 512, num_virtual_servers = 9)
bookkeeping = {"N": 0, "schema": {}, "shards": [], "servers": {}}
shard_mappers = {}

def has_keys(json_data : dict, keys : list):
    
    for key in keys:
        if key not in json_data.keys():
            return False
    
    return True
     
@app.route("/init", methods=["POST"])
def init():
    payload = json.loads(request.data)
    
    if not has_keys(payload, ["N","schema", "shards", "servers"]) or not has_keys(payload["schema"], ["columns", "dtypes"]) :
        return jsonify({
            "message" : "<Error> Payload not formatted correctly.",
            "status" : "failure"
        }), 200
    N = payload["N"]
    schema = payload["schema"]
    shards = payload["shards"]
    servers = payload["servers"]
    
    for shard in shards:
        shard_mappers[shard["Shard_id"]] = {
            "mapper" : consistentHash(0, 512, 9),
            "servers" : [],
            "curr_idx" : 0,
            "write_lock" : Lock(),
            "read_lock" : Lock()
        }
    
    bookkeeping["schema"]=schema
    bookkeeping["shards"]=shards
    
    
    cnt=0
    for s,v in servers.items():
        if '[' in s:
            name = "Server"+str(random.randint(0,1000))
        else:
            name = s
        while name in bookkeeping["servers"].keys():
            name = "Server"+str(random.randint(0,1000))
        bookkeeping["servers"][name] = v
        bookkeeping["N"]+=1
        os.popen(f'docker run --name {name} --network mynet --network-alias {name} -d server:latest').read()
        time.sleep(2)
        data_payload = {}
        data_payload["schema"] = schema
        data_payload["shards"] = v
        url=f"http://{name}:5000/config"
        try:
            r = requests.post(url, json=data_payload)
            print(r,flush=True)
        except:
            print("Server not reachable", flush = True)
        cnt+=1
    
    while cnt<N:
        name = "Server"+str(random.randint(0,1000))
        while name in bookkeeping["servers"].keys():
            name = "Server"+str(random.randint(0,1000))
        cur_shards = ["sh" + str(random.randint(1,len(shards))),"sh"+str(random.randint(1,len(shards)))]
        bookkeeping["servers"][name] = cur_shards
        bookkeeping["N"]+=1
        os.popen(f'docker run --name {name} --network mynet --network-alias {name} -d -p 5000 server:latest').read()
        time.sleep(2)
        data_payload = {}
        data_payload["schema"] = schema
        data_payload["shards"] = cur_shards
        url=f"http://{name}:5000/config"
        try:
            r = requests.post(url, json=data_payload)
            print(r,flush=True)
        except:
            print("Server not reachable", flush = True)
        cnt+=1
        
    for server, shards in bookkeeping["servers"].items():
        for shard_id in shards:
            shard_mappers[shard_id]["servers"].append(server)
            shard_mappers[shard_id]["mapper"].addServer(server)

    return jsonify({
        "message" : "Configured Database",
        "status" : "success"
    }) , 200

@app.route("/status", methods=["GET"])
def status():
    return jsonify(bookkeeping) , 200

@app.route("/add",methods=["POST"])
def add():
    payload = json.loads(request.data)
    
    if not has_keys(payload, ["n", "new_shards", "servers"]):
        return jsonify({
            "message" : "<Error> Payload not formatted correctly.",
            "status" : "failure"
        }), 200
    
    n = int(payload["n"])
    new_shards = payload["new_shards"]
    servers = payload["servers"]
    
    if n > len(servers):
        return jsonify({
            "message" : "<Error> Number of new servers (n) is greater than newly added instances",
            "status" : "failure"
        }), 200
    
    cnt=0
    msg = "Added "
    for s,v in servers.items():
        if '[' in s:
            name = "Server"+str(random.randint(0,1000))
        else:
            name = s
        while name in bookkeeping["servers"].keys():
            name = "Server"+str(random.randint(0,1000))
        bookkeeping["servers"][name] = v
        bookkeeping["N"]+=1
        # TODO - add new server and hit its config endpoint
        os.popen(f'docker run --name {name} --network mynet --network-alias {name} -d server:latest').read()
        time.sleep(2)
        data_payload = {}
        data_payload["schema"] = bookkeeping["schema"]
        data_payload["shards"] = v
        try:
            r = requests.post(f"http://{name}:5000/config", json=data_payload)
            print(r,flush=True)
        except:
            print("Server not reachable", flush = True)
        msg+=name
        cnt+=1
        if cnt == n:
            break
        else:
            msg+=" and "
    bookkeeping["shards"] += new_shards
    
    return jsonify({"N":bookkeeping["N"],
                    "message": msg,
                    "status": "successful"
                    }),200

@app.route("/rm", methods=["DELETE"])
def rm():

    payload = json.loads(request.data)
    
    if not has_keys(payload, ["n", "servers"]):
        return jsonify({
            "message" : "<Error> Payload not formatted correctly.",
            "status" : "failure"
        }), 200
        
    n = int(payload["n"])
    servers = payload["servers"]
    
    
    if n < len(servers):
        return jsonify({
            "message" : "<Error> wrong input n < len(servers).",
            "status" : "failure"
        }), 200
        
    
    # TODO - remove a server from the database

@app.route("/read", methods=["POST"])
def read():

    payload = json.loads(request.data)
    
    if not has_keys(payload, ["Stud_id"]) or not has_keys(payload["Stud_id"], ["low", "high"]):
        return jsonify({
            "message" : "<Error> Payload not formatted correctly.",
            "status" : "failure"
        }), 200
        
    low = int(payload["Stud_id"]["low"])
    high = int(payload["Stud_id"]["high"])
    
    shards_used = []
    data = []
    for shard in bookkeeping["shards"]:
        
        lo = shard["Stud_id_low"]
        hi = shard["Stud_id_low"] + shard["Shard_size"]
        
        
        if not (lo>high or hi< low):
            shards_used.append(shard["Shard_id"])
            ql = max(lo, low)
            qhi = min(hi, high)
            shard_id = shard["Shard_id"]
            requestID = random.randint(100000, 999999)
            server, _ = shard_mappers[shard_id]["mapper"].addRequest(requestID)
            data_payload = {"shard":shard_id, "Stud_id":{"low":ql, "high":qhi}}
            if not shard_mappers[shard_id]["write_lock"].locked():
                shard_mappers[shard_id]["read_lock"].acquire()
                try:
                    url=f"http://{server}:5000/read"
                    r = requests.post(url, json=data_payload)
                    print(r,flush=True)
                    data.extend(r.json()["data"])
                except:
                    print("Server not reachable", flush = True)
                    
                shard_mappers[shard_id]["read_lock"].release()
    return jsonify({
            "shards_queried": shards_used,
            "data": data,
            "status": "success"
        }),200
    
@app.route("/write", methods=["POST"])
def write():
    payload = json.loads(request.data)
    data = payload["data"]
    shard_data = {}
    
    for record in data:
        for shard in bookkeeping["shards"]:
            if record["Stud_id"] >= shard["Stud_id_low"] and record["Stud_id"] < shard["Stud_id_low"] + shard["Shard_size"]:
                shard_id = shard["Shard_id"]
                
                if shard_id in shard_data.keys():
                    shard_data[shard_id].append(record)
                else:
                    shard_data[shard_id] = [ record ]
                    
    for shard_id, records in shard_data.items():
        
        shard_mappers[shard_id]["read_lock"].acquire()
        shard_mappers[shard_id]["write_lock"].acquire()
        data_payload = {
            "shard" : shard_id,
            "curr_idx" : shard_mappers[shard_id]["curr_idx"],
            "data" : records
        }
        for server in shard_mappers[shard_id]["servers"]:
            try:
                r = requests.post(f"http://{server}:5000/write", json=data_payload)
                print(r,server)
            except:
                print(f"Server {server} not reachable", flush = True)
        shard_mappers[shard_id]["read_lock"].release()
        shard_mappers[shard_id]["write_lock"].release()

    return jsonify({
        "message" : f"{len(data)} Data entries added",
        "status" : "success"
        }), 200

@app.route("/update", methods=["PUT"])
def update():
    
    payload = json.loads(request.data) 
    stud_id = payload["Stud_id"]
    data = payload["data"]
    
    for shard in bookkeeping["shards"]:
        if stud_id >= shard["Stud_id_low"] and stud_id < shard["Stud_id_low"] + shard["Shard_size"]:
            
            shard_id = shard["Shard_id"]
            data_payload = {"shard":shard_id,"Stud_id":stud_id, "data":data}
            
            shard_mappers[shard_id]["read_lock"].acquire()
            shard_mappers[shard_id]["write_lock"].acquire()
            
            for server in shard_mappers[shard_id]["servers"]:
                try:
                    r = requests.put(f"http://{server}:5000/update", json=data_payload)
                    print(r,flush=True)
                except:
                    print(f"update at {server} for shard {shard_id} failed")    
                
            shard_mappers[shard_id]["read_lock"].release()
            shard_mappers[shard_id]["write_lock"].release()    
            
            
    return jsonify({
            "message" : f"Data updated for Stud_id : {stud_id} updated",
            "status" : "success"
        }),200
    
@app.route("/del", methods=["DELETE"])
def delete():
    
    payload = json.loads(request.data)
    stud_id = payload["Stud_id"]
    
    for shard in bookkeeping["shards"]:
        if stud_id >= shard["Stud_id_low"] and stud_id < shard["Stud_id_low"] + shard["Shard_size"]:
            
            shard_id = shard["Shard_id"]
            data_payload = {"shard":shard_id,"Stud_id":stud_id}
            
            shard_mappers[shard_id]["read_lock"].acquire()
            shard_mappers[shard_id]["write_lock"].acquire()
            
            for server in shard_mappers[shard_id]["servers"]:
                try:
                    r = requests.delete(f"http://{server}:5000/del", json=data_payload)
                    print(r,flush=True)
                except:
                    print(f"deletion at {server} for shard {shard_id}, Student {stud_id} failed.")
                    
            shard_mappers[shard_id]["read_lock"].release()
            shard_mappers[shard_id]["write_lock"].release() 
    
    return jsonify({
        "message" : f"Data entry with Stud_id:{stud_id} removed from all replicas",
        "status" : "success"
    }), 200

if __name__ == "__main__":
    app.run( host = "0.0.0.0", port = 5000, debug = True)