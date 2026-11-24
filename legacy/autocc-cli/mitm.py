import asyncio
import json
import random
from multiprocessing import Process

import numpy as np
from mitmproxy import http
from mitmproxy.options import Options
from mitmproxy.tools.dump import DumpMaster

from config import RAW_DIR, shared_read, attach_shared_namespace, shared_write


def save_request(flow, body_json):
	headers = dict(flow.request.headers)
	# 重放时由 requests 自动计算长度与连接信息
	headers.pop("Content-Length", None)
	headers.pop("Host", None)
	headers.pop("Connection", None)
	target_dict = {
		'url': flow.request.pretty_url,
		'headers': headers,
		'body': body_json,
	}
	href = shared_read().get('current_herf')
	ID = href.split("id=")[-1]
	np.save(str(RAW_DIR / f"{ID}.npy"), target_dict)


class InterceptXAPIRequest:
	"""拦截 info=core_xapi_statement_post 的请求"""

	def request(self, flow: http.HTTPFlow) -> None:
		# 方法1: 直接检查URL字符串
		if "info=core_xapi_statement_post" in flow.request.pretty_url:
			self._handle_intercepted_request(flow)
			return

	def _handle_intercepted_request(self, flow):
		"""处理被拦截的请求"""
		request_body = flow.request.get_text()
		level_1_json = json.loads(request_body)
		level_2_str = level_1_json[0]['args']['requestjson']
		datas = json.loads(level_2_str)
		total_time = 0
		for data in datas:
			random_time = round(random.uniform(15, 20), 2)
			total_time += random_time
			if "correctResponsesPattern" in data["object"]["definition"]:
				raw_ans = data["object"]["definition"]["correctResponsesPattern"][0]
				data["result"]["response"] = raw_ans
			max_score = data["result"]["score"]["max"]
			data["result"]["score"]["raw"] = max_score
			data["result"]["score"]["scaled"] = 1
			if "duration" in data["result"]:
				data["result"]["duration"] = "PT" + str(random_time) + "S"
			if "success" in data["result"]:
				data["result"]["success"] = True
		modified_request_json = json.dumps(datas)
		level_1_json[0]['args']['requestjson'] = modified_request_json
		modified_request_body = json.dumps(level_1_json)
		flow.request.set_text(modified_request_body)
		save_request(flow, level_1_json)
		index = shared_read().get('current_index') or "-"
		print(f"已修改第{index}道题目的请求，自动填写答案并设置满分，大约为你省去了{round(total_time, 2)}秒。")
		shared_write({'succeed': True})


async def config_mitmproxy(listen_host='127.0.0.1', listen_port=8888):
	"""配置 mitmproxy 参数与启动"""
	options = Options(listen_host=listen_host, listen_port=listen_port)
	script = InterceptXAPIRequest()
	addons = [script]

	# 创建 DumpMaster 实例，关闭终端日志与流量转储
	master = DumpMaster(options, with_termlog=False, with_dumper=False)
	master.addons.add(*addons)
	try:
		await master.run()  # 启动 mitmproxy 主循环
	except KeyboardInterrupt:
		master.shutdown()  # 当手动中断时，关闭 master


def run_mitmproxy(listen_host: str, listen_port: int, shared_ns):
	"""运行 mitmproxy"""
	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	# 在子进程中附加共享的索引代理，使 get_current_index() 能读取共享值
	attach_shared_namespace(shared_ns)
	loop.run_until_complete(config_mitmproxy(listen_host, listen_port))
	loop.close()


_manager = None


def start_mitmproxy(listen_host: str, listen_port: int) -> Process:
	"""启动 mitmproxy"""
	print("Start Mitmproxy")
	from multiprocessing import Manager
	global _manager
	_manager = Manager()
	shared_ns = _manager.Namespace()
	shared_ns.current_index = None
	shared_ns.current_title = None
	# 如需共享更多数据，可在此为 shared_ns 添加新的属性，例如：shared_ns.user_id = None
	# 在父进程内附加共享代理，以便 set_current_index() 同步到该代理
	attach_shared_namespace(shared_ns)
	mitmproxy_process = Process(target=run_mitmproxy, args=(listen_host, listen_port, shared_ns,))
	mitmproxy_process.start()
	print("Mitmproxy is running")
	return mitmproxy_process


def stop_mitmproxy(process: Process):
	"""停止 mitmproxy"""
	if process:
		process.terminate()
		process.join()
	# 关闭 Manager 以清理资源
	global _manager
	if _manager is not None:
		_manager.shutdown()
		_manager = None
	print('Mitmproxy Normal Exit')
	return


if __name__ == '__main__':
	import time

	mitmproxy_process = start_mitmproxy("127.0.0.1", 8800)  # 启动 mitmproxy
	time.sleep(30)  # 延迟30s后，关闭 mitmproxy
	stop_mitmproxy(mitmproxy_process)  # 停止 mitmproxy
