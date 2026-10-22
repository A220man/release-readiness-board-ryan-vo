import {beforeEach,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {CriterionEditor} from './CriteriaPanel';
import {ApprovalsPanel} from './ApprovalsPanel';
import {InsightsPanel} from './InsightsPanel';
import {ReleaseNotesPreview} from './ReleaseNotesPreview';
import {api} from './api';
import {Criterion,Release,User} from './types';
import App from './App';

vi.mock('./api',()=>({api:vi.fn(),download:vi.fn()}));
beforeEach(()=>vi.resetAllMocks());

const criterion:Criterion={id:'c1',name:'Security tests',description:'',category:'security',status:'pending',required:true,evidence:'',evidence_url:'',assigned_to:'',reviewed_by:''};
const user:User={subject:'creator',username:'Creator',roles:['reviewer'],csrf_token:'fixture'};
const release={id:'r1',created_by:'creator',status:'in_review',revision:3} as Release;

it('requires saved evidence before a pass review',()=>{
  render(<CriterionEditor item={criterion} editable refresh={vi.fn()}/>);
  expect(screen.getByText('Pass review')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Evidence for Security tests'),{target:{value:'Job 42 passed'}});
  expect(screen.getByText('Pass review')).toBeDisabled();
});

it('saves evidence and refreshes the persisted state',async()=>{
  vi.mocked(api).mockResolvedValue({});
  const refresh=vi.fn();
  render(<CriterionEditor item={criterion} editable refresh={refresh}/>);
  fireEvent.change(screen.getByLabelText('Evidence for Security tests'),{target:{value:'Job 42 passed'}});
  fireEvent.click(screen.getByText('Save evidence'));
  await waitFor(()=>expect(refresh).toHaveBeenCalledOnce());
  expect(api).toHaveBeenCalledWith('/api/criteria/c1','PUT',{evidence:'Job 42 passed',assigned_to:''});
});

it('prevents the creator from recording their own approval',()=>{
  render(<ApprovalsPanel release={release} items={[]} user={user} refresh={vi.fn()}/>);
  expect(screen.queryByText('Record decision')).not.toBeInTheDocument();
  expect(screen.getByText(/An independent reviewer can record/)).toBeInTheDocument();
});

it('distinguishes historical approval revisions',()=>{
  render(<ApprovalsPanel release={release} user={user} refresh={vi.fn()} items={[{id:'a1',approver:'second',role:'operator',decision:'approved',release_revision:2,conditions:'',comment:'Old evidence',created_at:'2026-01-01'}]} />);
  expect(screen.getByText(/Historical \/ superseded/)).toBeInTheDocument();
});

it('requires consent before optional advice',async()=>{
  vi.mocked(api).mockResolvedValue({analysis:'Check coverage'});
  render(<InsightsPanel rid="r1" risk={null} audit={[]} editable />);
  expect(screen.getByText('Request advice')).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByText('Request advice'));
  await waitFor(()=>expect(api).toHaveBeenCalledWith('/api/llm/analyze/r1','POST',{consent:true}));
});

it('supports search query and status filter in workspace list',async()=>{
  vi.mocked(api).mockImplementation(async(url:string)=>{
    if(url==='/api/auth/mode')return{mode:'demo'};
    if(url==='/api/auth/me')return user;
    if(url.startsWith('/api/releases/'))return{items:[],total:0};
    return{};
  });
  render(<App/>);
  await waitFor(()=>expect(screen.getByPlaceholderText('Search by name or description…')).toBeInTheDocument());
  fireEvent.change(screen.getByPlaceholderText('Search by name or description…'),{target:{value:'Payment'}});
  fireEvent.change(screen.getByLabelText('Status'),{target:{value:'in_review'}});
  fireEvent.click(screen.getByText('Search'));
  await waitFor(()=>{
    expect(api).toHaveBeenCalledWith(expect.stringContaining('search=Payment'));
    expect(api).toHaveBeenCalledWith(expect.stringContaining('status=in_review'));
  });
  expect(screen.getByText('No releases match the active filter or search query.')).toBeInTheDocument();
});

it('opens release notes preview and fetches notes on demand',async ()=>{
  const notes={
    release_name:'Test Release',version:'1.0.0',status:'approved',evidence_revision:2,
    date:'2026-12-01',summary:'Test summary',
    criteria_results:[{name:'Security tests',status:'passed',required:true,evidence:'Job 42 passed'}],
    blockers_resolved:[],blockers:[],
    approvals:[{approver:'reviewer',decision:'approved',release_revision:2,comment:'Looks good'}],
    risk_assessment:{risk_score:12,risk_level:'low',ready_for_release:true,risk_factors:[],recommendations:[],features:{}},
    generated_at:new Date().toISOString()
  };
  vi.mocked(api).mockResolvedValue(notes);
  render(<ReleaseNotesPreview rid="r1" open={true} onClose={vi.fn()}/>);
  expect(screen.getByText('Loading…')).toBeInTheDocument();
  await waitFor(()=>expect(screen.getByText(/Test Release/)).toBeInTheDocument());
  fireEvent.click(screen.getByRole('tab',{name:'Criteria'}));
  await waitFor(()=>expect(screen.getByText(/Security tests/)).toBeInTheDocument());
  expect(screen.getByText(/Job 42 passed/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('tab',{name:'Approvals'}));
  await waitFor(()=>expect(screen.getByText(/reviewer/)).toBeInTheDocument());
  expect(screen.getByText(/Looks good/)).toBeInTheDocument();
  expect(api).toHaveBeenCalledWith('/api/releases/r1/release-notes');
});