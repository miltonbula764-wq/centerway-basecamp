import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { LiveOperation } from '@/components/cw/live-operation';
import { L01Error } from '@/data/transport';
const h=vi.hoisted(()=>({prepare:vi.fn(),submit:vi.fn(),refresh:vi.fn(),invalidate:vi.fn(),allowed:true}));
vi.mock('@tanstack/react-router',()=>({useRouter:()=>({invalidate:h.invalidate})}));
vi.mock('@/components/cw/live-session',()=>({useLiveSession:()=>({runtime:{prepare:h.prepare,submit:h.submit,refresh:h.refresh,controller:{canAttempt:()=>h.allowed,state:{client:'c'}}},state:{auth:{status:'authenticated',tenant:'t',session:{principal:'p'}}}})}));
const draft={principal:'p',tenant:'t',client:'c',request:{request_id:'same-request',operation:'investigate',arguments:{}},lastError:null};
const element=()=> <LiveOperation client="c" operation="investigate" arguments={{investigation_id:'i',as_of:'2026-10-31T12:00:00Z'}} label="Investigar caso" />;
beforeEach(()=>{vi.clearAllMocks();h.allowed=true;h.prepare.mockResolvedValue(draft);h.submit.mockResolvedValue({request_id:'same-request',status:'processed'});h.refresh.mockResolvedValue(undefined);h.invalidate.mockResolvedValue(undefined);});
describe('explicit API operation confirmation',()=>{
 it('does not prepare or submit without permission',()=>{h.allowed=false;render(element());expect(screen.getByRole('button',{name:'Investigar caso'})).toBeDisabled();expect(h.prepare).not.toHaveBeenCalled();expect(h.submit).not.toHaveBeenCalled();});
 it('requires confirmation and preserves the real receipt until the dialog closes',async()=>{render(element());fireEvent.click(screen.getByRole('button',{name:'Investigar caso'}));const send=await screen.findByRole('button',{name:'Confirmar envio'});expect(send).toBeDisabled();expect(h.submit).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(send);await screen.findByRole('status');expect(h.submit).toHaveBeenCalledExactlyOnceWith('same-request');expect(h.refresh).not.toHaveBeenCalled();expect(screen.getByRole('status')).toHaveTextContent('processed');});
 it('never automatically repeats an uncertain POST; explicit resend uses same request id',async()=>{h.submit.mockRejectedValueOnce(new L01Error('network',null,'unavailable')).mockResolvedValueOnce({request_id:'same-request'});render(element());fireEvent.click(screen.getByRole('button',{name:'Investigar caso'}));await screen.findByRole('button',{name:'Confirmar envio'});fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByRole('button',{name:'Confirmar envio'}));const retry=await screen.findByRole('button',{name:'Reenviar exatamente o mesmo pedido'});expect(h.submit).toHaveBeenCalledTimes(1);fireEvent.click(retry);await waitFor(()=>expect(h.submit).toHaveBeenCalledTimes(2));expect(h.submit.mock.calls).toEqual([['same-request'],['same-request']]);expect(h.prepare).toHaveBeenCalledTimes(1);});
});
