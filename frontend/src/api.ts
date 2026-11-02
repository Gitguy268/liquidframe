export type Asset={id:string;root_id:string;relative_path:string;name:string;extension:string;title?:string;caption?:string;keywords?:string[];rating?:number;pick_state?:string;color_label?:string;hidden?:number;deleted_at?:number;imported_at?:number;edited_at?:number;viewed_at?:number;latitude?:number;longitude?:number;place?:string;stack_id?:string;stack_count?:number;media_kind?:string;duration?:number;match_time?:number;camera?:string;lens?:string;size:number;revision:number;recipe_version?:number;width:number;height:number;bits:number;captured:string;status:string;error?:string;favorite:number;metadata:Record<string,any>};
export type Root={id:string;name:string;path:string;kind:string};
export type Job={id:string;kind:string;state:string;progress:number;message:string;error?:string;result:any;created:number};
export type Recipe={schema_version?:number;frame?:number;adjustments?:Record<string,any>;raw?:Record<string,any>;engine?:Record<string,any>;video?:Record<string,any>;operations?:{tool:string;result:string;adjustments:Record<string,any>;precision?:string}[]};
export type AppState={stats:{total:number;favorites:number;bytes:number;missing:number;indexed:number};roots:Root[];albums:any[];models:{id:string;label:string;bytes:number;installed:boolean;license:string}[];settings:{theme:string;glass:boolean;cache_gb:number;acceleration:string};jobs:Job[]};
export type Selection={ids?:string[];selection_id?:string;exclude_ids?:string[]};
export const getLibrary=()=>localStorage.getItem('liquidframe-library')||'default';
export const setLibrary=(id:string)=>localStorage.setItem('liquidframe-library',id);
export const endpoint=(path:string)=>'/api/v1'+path+(path.includes('?')?'&':'?')+'library='+encodeURIComponent(getLibrary());
export async function api<T=any>(path:string,method='GET',body?:unknown):Promise<T>{
 const request={method,headers:{'Content-Type':'application/json','X-Openphoto':'1','X-Library-ID':getLibrary()},body:body===undefined?undefined:JSON.stringify(body)};
 let response=await fetch(endpoint(path),request);
 if(response.status===401){await fetch('/',{cache:'no-store'});response=await fetch(endpoint(path),request);}
 if(!response.ok){const data=await response.json().catch(()=>({detail:'The local helper could not complete this request.'}));throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));}
 return response.json();
}
export const thumbnail=(id:string,size=256,version='')=>endpoint(`/assets/${id}/thumbnail?size=${size}${version?'&version='+encodeURIComponent(version):''}`);
export const bytes=(n:number)=>n>1e9?`${(n/1e9).toFixed(1)} GB`:n>1e6?`${(n/1e6).toFixed(1)} MB`:`${Math.round(n/1e3)} KB`;
export async function upload(files:File[]){const data=new FormData();files.forEach(f=>data.append('files',f));const r=await fetch(endpoint('/imports/upload'),{method:'POST',headers:{'X-Openphoto':'1'},body:data});if(!r.ok)throw new Error((await r.json()).detail);return r.json();}
