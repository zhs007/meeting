Howto
=====

## 运行


### 调用语音同传AST
```
go run . --target=ast \
--host=wss://openspeech.bytedance.com \
--endpoint=v4/ast/v2/translate \
--resource_id=volc.service_type.10053 \
--app_id=<app_id> \
--access_key=<access_key>
```