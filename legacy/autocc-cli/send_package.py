import requests

def send_request(request:dict)->bool:
	try:
		response = requests.post(
			url=request['url'],
			headers=request['headers'],
			json=request['body'],  # 如果发送表单数据
			timeout=10,
		)

		if response.status_code == 200 and "\"error\":false" in response.text:
			return True
		else:
			return False
	except requests.exceptions.RequestException as e:
		return False
