import json
import workflow as wf

def lambda_handler(event, context):
    print(json.dumps(event))

    param_map = json.loads(event['Records'][0]['Sns']['Message'])

    command = param_map['command']
    params = param_map['params']
    response_url = param_map['response_url']

    result = "Hello from Lambda!!"

    wf.run(cmd=params[1], mr_id=int(params[2]), response_url=response_url)

    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }

