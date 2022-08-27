import json
import workflow as wf
import os
import boto3

def lambda_handler(event, context):
    print(json.dumps(event))

    param_map = json.loads(event['Records'][0]['Sns']['Message'])

    command = param_map['command']
    params = param_map['params']
    response_url = param_map['response_url']
    retry_count = param_map['retry_count']

    result = "Hello from Lambda!!"

    workflow_status_webhook = os.environ.get("workflow_status_webhook")
    if workflow_status_webhook is None:
        workflow_status_webhook = response_url

    run_output = wf.run(cmd=params[1], \
                        mr_id=int(params[2]), \
                        response_url=response_url, \
                        workflow_status_webhook=workflow_status_webhook,
                        project_alias=params[0])

    if retry_count is not None and retry_count <= 5 and run_output is not None and 'result' in run_output:
        print("Approve Merge Pipeline operation result found")
        result = run_output['result']
        if 'APPROVAL_STATUS' in result and result['APPROVAL_STATUS'] == 'RM_APPROVED':
            # publish to sns topic with retry_count + 1
            print(f"Retry_Count {retry_count}, Approval status {result['APPROVAL_STATUS']}, Publishing to SNS again")
            message = {}
            message['command'] = command
            message['params'] = params
            message['response_url'] = response_url
            message['retry_count'] = retry_count + 1
            sns_client = boto3.client('sns')
            sns_client.publish(
                TopicArn='arn:aws:sns:ap-southeast-1:621715770769:release_approval_sns',
                Message=json.dumps({'default' : json.dumps(message)}),
                MessageStructure='json')

    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }

