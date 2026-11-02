import icons from './aiko.json';
const aliases:Record<string,string>={photos:'images',album:'folder',favorites:'heart-user',people:'users',duplicates:'overlapping-squares',adjust:'sliders',cleanup:'paintbrush',background:'image-sparkle',enhance:'sparkles',crop:'frame',info:'info-circle',refresh:'refresh',zoom:'search',clock:'time'};
export function Icon({name,size=20}:{name:string;size?:number}){
 const data=(icons as Record<string,Record<string,string>>)[aliases[name]||name]||(icons as any)['image'];
 const {id,viewBox,...attrs}=data;
 return <svg width={size} height={size} viewBox={viewBox} {...attrs} aria-hidden="true" className="icon"><use href={`/aiko.svg#${id}`}/></svg>;
}
