// Base para futura aplicação React Native.
export type OfflineEvent={deviceId:string;eventType:string;payload:Record<string,unknown>;createdAt:string};
export class OfflineQueue{private queue:OfflineEvent[]=[];add(e:OfflineEvent){this.queue.push(e)}pending(){return[...this.queue]}markSynced(e:OfflineEvent){this.queue=this.queue.filter(x=>x!==e)}}
