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

let unroll = ref 20;;
let fun_unroll = ref 50;;
let loglevel = ref 3;;
let module_loglevel: (string, int) Hashtbl.t = Hashtbl.create 5;;

  
(* set of values that will not be explored as values of the instruction pointer *)
module SAddresses = Set.Make(Z)
let blackAddresses = ref SAddresses.empty

type memory_model_t =
  | Flat
  | Segmented

let memory_model = ref Flat

type format_t =
  | Pe
  | Elf
  | Binary

type archi_t =
  | X86
  | ARMv7
  | ARMv8 (* ARMv8-A *)

let architecture = ref X86;;

type endianness_t =
  | LITTLE
  | BIG

let endianness = ref LITTLE;;

type mode_t =
  | Protected
  | Real

type analysis_src =
  | Bin
  | Cfa

type analysis_t =
  | Forward of analysis_src
  | Backward

let analysis = ref (Forward Bin);;

let mode = ref Protected

let in_mcfa_file = ref "";;
let out_mcfa_file = ref "";;
  
let load_mcfa = ref false;;
let store_mcfa = ref false;;

(* name of binary file to analyze *)
let binary = ref "";;

let format = ref Pe

type call_conv_t =
  | CDECL
  | STDCALL
  | FASTCALL

let call_conv = ref CDECL

let text = ref ""
let code_length = ref 0
let ep = ref Z.zero
let phys_code_addr = ref 0
let rva_code = ref Z.zero

let address_sz = ref 32
let operand_sz = ref 32
let size_of_long () = !operand_sz
let stack_width = ref 32

let gdt: (Z.t, Z.t) Hashtbl.t = Hashtbl.create 19

let cs = ref Z.zero
let ds = ref Z.zero
let ss = ref Z.zero
let es = ref Z.zero
let fs = ref Z.zero
let gs = ref Z.zero

(* if true then an interleave of backward then forward analysis from a CFA will be processed *)
(** after the first forward analysis from binary has been performed *) 
let interleave = ref false
  
type tvalue =
  | Taint of Z.t * Taint.id_t
  | TMask of Z.t * Z.t * Taint.id_t (* second element is a mask on the first one *)

type cvalue =
  | Content of Z.t
  | CMask of Z.t * Z.t
  | Bytes of string
  | Bytes_Mask of (string * Z.t)

let reg_override: (Z.t, ((string * (Register.t -> tvalue)) list)) Hashtbl.t = Hashtbl.create 5
let mem_override: (Z.t, (Z.t * tvalue) list) Hashtbl.t = Hashtbl.create 5
let stack_override: (Z.t, (Z.t * tvalue) list) Hashtbl.t = Hashtbl.create 5
let heap_override: (Z.t, (Z.t * tvalue) list) Hashtbl.t = Hashtbl.create 5
  
    
(* tables for the initialisation of the global memory, stack and heap *)
(* first element in the key is the address ; second one is the number of repetition *)
type ctbl = (Z.t * int, cvalue * (tvalue option)) Hashtbl.t

let register_content: (string, (Register.t -> cvalue * tvalue option)) Hashtbl.t = Hashtbl.create 10
let memory_content: ctbl = Hashtbl.create 10
let stack_content: ctbl = Hashtbl.create 10
let heap_content: ctbl = Hashtbl.create 10

type sec_t = (Z.t * Z.t * Z.t * Z.t * string) list ref
let sections: sec_t = ref []
  
let import_tbl: (Z.t, (string * string)) Hashtbl.t = Hashtbl.create 5

(* tainting and typing rules for functions *)
type taint_t =
  | No_taint
  | Buf_taint
  | Addr_taint
      

(** data stuctures for the assertions *)
let assert_untainted_functions: (Z.t, taint_t list) Hashtbl.t = Hashtbl.create 5
let assert_tainted_functions: (Z.t, taint_t list) Hashtbl.t = Hashtbl.create 5

(** data structure for the tainting rules of import functions *)
let tainting_rules : ((string * string), (call_conv_t * taint_t option * taint_t list)) Hashtbl.t = Hashtbl.create 5


(** data structure for the typing rules of import functions *)
let typing_rules : (string, TypedC.ftyp) Hashtbl.t = Hashtbl.create 5

let clear_tables () =
  Hashtbl.clear assert_untainted_functions;
  Hashtbl.clear assert_tainted_functions;
  Hashtbl.clear memory_content;
  Hashtbl.clear stack_content;
  Hashtbl.clear heap_content;
  Hashtbl.clear import_tbl;
  Hashtbl.clear reg_override;
  Hashtbl.clear mem_override;
  Hashtbl.clear stack_override;
  Hashtbl.clear heap_override
