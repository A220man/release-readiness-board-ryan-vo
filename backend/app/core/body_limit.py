from fastapi.responses import JSONResponse

class BodyLimit:
    def __init__(self,app,limit):self.app=app;self.limit=limit
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        messages=[];size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            size+=len(message.get('body',b''))
            if size>self.limit:
                return await JSONResponse({'error':{'code':'request_too_large','message':'Request exceeds the configured body limit'}},status_code=413)(scope,receive,send)
            messages.append(message)
            if not message.get('more_body',False):break
        async def replay():
            if messages:return messages.pop(0)
            return await receive()
        await self.app(scope,replay,send)


