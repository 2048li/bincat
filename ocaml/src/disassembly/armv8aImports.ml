(*
    This file is part of BinCAT.
    Copyright 2014-2017 - Airbus Group

    BinCAT is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or (at your
    option) any later version.

    BinCAT is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with BinCAT.  If not, see <http://www.gnu.org/licenses/>.
*)

module Make(D: Domain.T)(Stubs: Stubs.T with type domain_t := D.t) =
struct

  open Asm

  let reg r = V (T (Register.of_name r))

  let const x sz = Const (Data.Word.of_int (Z.of_int x) sz)

  let tbl: (Data.Address.t, import_desc_t) Hashtbl.t = Hashtbl.create 5

  let aapcs_calling_convention = {
    return = reg "x0" ;
    callee_cleanup = (fun _x -> []) ;
    arguments = function
    | 0 -> Lval (reg "x0")
    | 1 -> Lval (reg "x1")
    | 2 -> Lval (reg "x2")
    | 3 -> Lval (reg "x3")
    | 4 -> Lval (M (Lval (reg "sp"), 32))
    | n -> Lval (M ((BinOp (Add, Lval (reg "sp"), const ((n-5)*4) 32)), 32)) ;
  }


  let typing_rule_stmts_from_name name =
    try
      let _rule = Hashtbl.find Config.typing_rules name in
      [], []
    with
    | _ -> [], []

  let tainting_stmts_from_name libname name =
    try
      let _callconv,ret,args = Hashtbl.find Config.tainting_rules (libname,name) in
      let taint_arg taint =
        match taint with
        | Config.No_taint -> []
        | Config.Buf_taint -> [ Directive (Taint (None, M (Lval (reg "x0"), 
                                                           !Config.operand_sz))) ]
        | Config.Addr_taint -> [ Directive (Taint (None, (reg "x0"))) ]
      in
      let taint_ret_stmts =
        match ret with
        | None -> []
        | Some t -> taint_arg t
      in
      let _taint_args_stmts =
        List.fold_left (fun l arg -> (taint_arg arg)@l) [] args
      in
      [], taint_ret_stmts @ taint_ret_stmts
    with
    | _ -> [], []


  let stub_stmts_from_name name =
    if  Hashtbl.mem Stubs.stubs name then
      [
        Directive (Stub (name, aapcs_calling_convention)) ;
        Directive (Forget (reg "x1")) ;
        Directive (Forget (reg "x2")) ;
        Directive (Forget (reg "x3")) ;
      ]

    else
      [
        Directive (Forget (reg "x0")) ;
        Directive (Forget (reg "x1")) ;
        Directive (Forget (reg "x2")) ;
        Directive (Forget (reg "x3")) ;
      ]

  let init_imports () =
    Hashtbl.iter (fun adrs (libname,fname) ->
      let typing_pro,typing_epi = typing_rule_stmts_from_name fname in
      let tainting_pro,tainting_epi = tainting_stmts_from_name libname fname  in
      let stub_stmts = stub_stmts_from_name fname in
      let fundesc:Asm.import_desc_t = {
        name = fname ;
        libname = libname ;
        prologue = typing_pro @ tainting_pro ;
        stub = stub_stmts ;
        epilogue = typing_epi @ tainting_epi ;
        ret_addr = Lval(reg "lr") ;
      } in
      Hashtbl.replace tbl (Data.Address.global_of_int adrs) fundesc
    ) Config.import_tbl



  let init () =
    Stubs.init ();
    init_imports ()


end
