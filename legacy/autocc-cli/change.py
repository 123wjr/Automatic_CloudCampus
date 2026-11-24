def change_content(flow:dict, data:dict)->dict:
	"""
	替换agent中的name值
	"""

	# 查找并替换
	import json
	body = flow['body']
	requesttext = body[0]['args']['requestjson']
	requestjson:list[dict] = json.loads(requesttext)
	for item in requestjson:
		item["actor"]["name"]=data['nickname']
		item["actor"]["account"]["name"]=data['user_id']

	# 将修改后的requestjson重新转换为字符串
	updated_requesttext = json.dumps(requestjson)
	body[0]['args']['requestjson'] = updated_requesttext
	flow['body'] = body

	# 替换cookie
	flow['headers']['Cookie'] = data['Cookie']

	# 替换sesskey
	# 处理两种格式的sesskey：
	# 1. URL查询参数格式: sesskey=7pcJvQplAy
	import re
	sesskey_url_pattern = r'(sesskey=)[^&\s\r\n]*'
	if re.search(sesskey_url_pattern, flow['url']):
		flow['url'] = re.sub(sesskey_url_pattern, f'\\g<1>{data["sesskey"]}', flow['url'])

	return flow