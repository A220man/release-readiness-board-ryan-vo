let csrf='';
export function setCsrf(value:string){csrf=value;}
export async function api<T>(url:string,method='GET',body?:unknown):Promise<T>{
 const response=await fetch(url,{method,credentials:'include',headers:{'Content-Type':'application/json',...(method==='GET'?{}:{'X-CSRF-Token':csrf})},body:body===undefined?undefined:JSON.stringify(body)});
 if(!response.ok){let message=`Request failed (${response.status})`;try{const data=await response.json();message=data.error?.message||(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail))||message;}catch{}throw new Error(message);}
 return response.status===204?undefined as T:response.json();
}
export async function download(url:string,name:string){const response=await fetch(url,{credentials:'include'});if(!response.ok)throw new Error('Download failed');const object=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=object;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(object),1000);}
