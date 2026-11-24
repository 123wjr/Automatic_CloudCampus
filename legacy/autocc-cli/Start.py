from query import query
from main import main
from resend import resend_package

if __name__ == "__main__":
	flag=input("请输入操作类型，1查询用户进度，2进行首次完成，3进行重复发包")
	if flag=="1":
		query()
	if flag=="2":
		main()
	if flag=="3":
		resend_package()