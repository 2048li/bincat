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

(* Log module for init_check *)

module L = Log.Make(struct let name = "init_check" end)

open Config

(* checkers for both init state creation and further overrides *)

let check_content b sz name =
  if (String.length (Bits.z_to_bit_string b)) > sz then
	L.abort (fun p -> p "Illegal initialisation/override for register %s" name)
	  
let check_mask b m sz name =
  if (String.length (Bits.z_to_bit_string b)) > sz || (String.length (Bits.z_to_bit_string m)) > sz then
	    L.abort (fun p -> p "Illegal initialization/override for register %s" name)
    
(* checks whether the provided value is compatible with the capacity of the parameter of type Register *)
let check_register_init r (c, t) =
  let sz   = Register.size r in
  let name = Register.name r in
  begin
	match c with
	| Content c    -> check_content c sz name
	| CMask (b, m) -> check_mask b m sz name
	| _ -> L.abort (fun p -> p "Illegal memory init \"|xx|\" spec used for register")
  end;
  begin
	match t with
	| Some (Taint (c, _taint_src))    -> check_content c sz name
	| Some (TMask (b, m, _taint_src)) -> check_mask b m sz name
	| _ -> ()
  end
