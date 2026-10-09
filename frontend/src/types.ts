export type User={subject:string;username:string;roles:string[];csrf_token:string};
export type Release={id:string;name:string;version:string;description:string;status:string;revision:number;target_date:string|null;created_by:string;risk_score:number;criteria_summary:{total:number;passed:number;required_total:number;required_passed:number};blocker_summary:{total:number;open:number;critical:number}};
export type Criterion={id:string;name:string;description:string;category:string;status:string;required:boolean;evidence:string;evidence_url:string;assigned_to:string;reviewed_by:string};
export type Blocker={id:string;title:string;description:string;severity:string;status:string;category:string;resolution:string;assigned_to:string};
export type Approval={id:string;approver:string;role:string;decision:string;release_revision:number;conditions:string;comment:string;created_at:string};
export type Risk={risk_score:number;risk_level:string;ready_for_release:boolean;risk_factors:string[];recommendations:string[];features:Record<string,number>;patterns?:unknown[]};
export type Audit={id:string;action:string;entity_type:string;details:string;user_id:string;timestamp:string;old_value:string;new_value:string};
