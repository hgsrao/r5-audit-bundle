"""Experimental native R5 execution factory with instance-local passive accounting.

Does not alter the sealed worker or its identity/holdout guard. The experimental
runner owns the manifest/Stage-B selection and calls this executor explicitly.
"""
from collections import Counter
from dataclasses import asdict, is_dataclass
from pathlib import Path
import json

class PassiveCounters:
    def __init__(self):
        self.rows = {}
    def observe(self, stage, side, passed, reason):
        row=self.rows.setdefault((stage,side),dict(input=0,passed=0,rejects=Counter()))
        row['input']+=1
        if passed: row['passed']+=1
        else: row['rejects'][str(reason)]+=1
    def report(self):
        result={}
        for (stage,side),row in sorted(self.rows.items()):
            rejects=dict(sorted(row['rejects'].items()))
            result.setdefault(stage,{})[side]=dict(input=row['input'],passed=row['passed'],rejects=rejects,
                accounting_closed=row['input']==row['passed']+sum(rejects.values()))
        return result

def attach_passive_counters(orch):
    """Each instance wrapper calls its captured bound original exactly once."""
    counters=PassiveCounters()
    original_id=orch.id_box.evaluate
    def evaluate_id(signal,*args,**kwargs):
        result=original_id(signal,*args,**kwargs)
        decision=result[0]
        side='BUY' if signal.direction>0 else 'SELL' if signal.direction<0 else 'NEUTRAL'
        stage='ID' if orch._native_bar_index>=0 else 'ID_WARMUP'
        counters.observe(stage,side,bool(decision.approved),decision.reason)
        return result
    orch.id_box.evaluate=evaluate_id
    original_governor=orch._governor_entry
    def evaluate_governor(*args,**kwargs):
        result=original_governor(*args,**kwargs)
        side=kwargs.get('side',args[3] if len(args)>3 else 'UNKNOWN')
        counters.observe('GOVERNOR',side,result['action']=='ENTRY',result.get('reason','UNSPECIFIED'))
        return result
    orch._governor_entry=evaluate_governor
    original_pre=orch.entry_decision_engine.evaluate_pre_submit
    def evaluate_pre(*args,**kwargs):
        result=original_pre(*args,**kwargs)
        signal=kwargs.get('signal')
        side='BUY' if signal.profit_target_price>signal.entry_price else 'SELL'
        counters.observe('PRE_SUBMIT',side,bool(result['passed']),f"{result.get('gate','UNKNOWN')}:{result.get('reason','UNSPECIFIED')}")
        for decision in result.get('decisions',[]):
            if decision.gate_name=='Gate12StrategySignals':
                counters.observe('GATE12_REACHED',side,bool(decision.passed),decision.reason)
                break
        return result
    orch.entry_decision_engine.evaluate_pre_submit=evaluate_pre
    return counters

def _json(path,value):
    Path(path).write_text(json.dumps(value,sort_keys=True,indent=2,default=lambda x:asdict(x) if is_dataclass(x) else str(x),allow_nan=False)+'\n')

def execute_block(root,protocol,block,params,*,combined_cycle_state_path=None,
                  output_path=None,fleet_loading_policy=None,feedback_compaction=False,
                  prepare=None):
    """Worker-compatible result plus full native report/accounting/receipts.

    Optional policy is a FleetLoadingPolicy instance supplied by the integrated
    C02 runtime. Unsupported source rejects the option instead of ignoring it.
    """
    from scripts import run_r5_step5_candidate as worker
    from canonical_parameter_registry import CanonicalParameterRegistry
    from revision2_external.grid_context import SealedGridContextProvider
    from revision2_external.orchestrator import Revision2ExternalEngineOrchestrator
    from revision5.ccpp_unified_plant import CentralPlantMasterDCS
    from revision5.paper_state_journal import PaperStateJournal
    import inspect
    if int(block['block'])!=1:
        raise ValueError('C05 acceptance factory is Block 1 only')
    if output_path is None:
        raise ValueError('Explicit isolated acceptance output path required')
    output=Path(output_path); output.mkdir(parents=True,exist_ok=True)
    frames,feeds,audit=(prepare or worker.prepare_block)(Path(root),protocol,block)
    registry=CanonicalParameterRegistry(); registry.verify_frozen_identity()
    errors=registry.validate_calibration_payload(params,engine='EXTERNAL')
    if errors: raise ValueError('; '.join(errors))
    provider=SealedGridContextProvider(feeds['NIFTY_50_15MIN'],feeds['INDIA_VIX_15MIN'])
    equity=float(protocol['block_execution_contract']['starting_equity_per_block'])
    plant=CentralPlantMasterDCS(total_capital=equity,db_path=':memory:')
    runtime=None; journal=None
    try:
        if combined_cycle_state_path is not None:
            runtime=worker.build_paper_combined_cycle_runtime(Path(combined_cycle_state_path))
        extra={}
        if fleet_loading_policy is not None:
            from revision5.fleet_loading_controller import FleetLoadingPolicy
            if not isinstance(fleet_loading_policy,FleetLoadingPolicy): raise TypeError('FleetLoadingPolicy required')
            if 'fleet_loading_policy' not in inspect.signature(Revision2ExternalEngineOrchestrator).parameters:
                raise RuntimeError('Fleet policy not integrated in loaded orchestrator')
            extra['fleet_loading_policy']=fleet_loading_policy
        if feedback_compaction:
            if 'feedback_compaction' not in inspect.signature(PaperStateJournal).parameters:
                raise RuntimeError('Feedback compaction not integrated in loaded journal')
            journal=PaperStateJournal(output/'paper_replay.sqlite3',feedback_compaction=True)
            extra['paper_journal']=journal
        orch=Revision2ExternalEngineOrchestrator(sorted(frames),registry,calibration_overrides=params,
            starting_equity=equity,grid_context_provider=provider,real_plant_dcs=plant,
            plant_control_mode='PAPER_APPLY',closed_loop_mode='active_paper',telemetry_mode='compact',
            governor_authority=protocol['engine'].get('governor_authority','advisory'),
            combined_cycle_runtime=runtime,**extra)
        counters=attach_passive_counters(orch)
        safety=dict(orch.safety_contract.values)
        report=orch.run(frames,warmup=int(protocol['block_execution_contract']['stock_warmup_bars_per_symbol']))
        accounting=counters.report()
        receipts=None
        if runtime is not None:
            receipts=dict(positions=[json.loads(r[0]) for r in runtime.store.connection.execute('SELECT payload FROM positions')],
                          conversions=runtime.store.requests(),handoff=asdict(runtime.handoff.config),
                          engine_b=asdict(runtime.engine_b.policy),runtime=asdict(runtime.config))
        _json(output/'native_report.json',report)
        _json(output/'passive_rejection_accounting.json',accounting)
        _json(output/'runtime_safety_contract.json',safety)
        _json(output/'runtime_receipts.json',receipts)
        metrics=worker.metrics(report)
        result=dict(audit=audit,metrics=metrics,plant_control=report['plant_control'],
            governor_authority=report['governor_authority'],micom=report['micom'],trades=report.get('trades',[]),
            passive_rejection_accounting=accounting,runtime_safety_contract=safety,
            native_report_path=str(output/'native_report.json'),runtime_receipts_path=str(output/'runtime_receipts.json'))
        if runtime is not None:
            result['combined_cycle_runtime']=dict(environment='paper',classification='EXPERIMENTAL_COMBINED_CYCLE',
                live_admissions=False,handoff=receipts['handoff'],engine_b=receipts['engine_b'],runtime=receipts['runtime'])
        canonical=dict(block=int(block['block']),sessions=block['sessions'],params=params,
            metrics=metrics,plant_control=report['plant_control'],governor_authority=report['governor_authority'],
            micom=report['micom'],trades=report.get('trades',[]),slice_sha256=audit['slice_sha256'])
        if runtime is not None: canonical['combined_cycle_runtime']=result['combined_cycle_runtime']
        result['block_fingerprint']=worker.canonical_json_hash(canonical)
        _json(output/'acceptance_result.json',result)
        return result
    finally:
        if journal is not None: journal.close()
        if runtime is not None: runtime.store.close()
