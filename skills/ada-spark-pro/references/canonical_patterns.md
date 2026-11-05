# Canonical SPARK Ada 2022 Reference Patterns

Complete, copy-ready SPARK Ada 2022 (`-gnat2022`, `SPARK_Mode => On`) reference patterns for safety-critical robotics OS kernels, MMIO hardware registers, Jorvik real-time concurrency, and hybrid Alire + CMake 4.4.3+ integration.

---

## 1. Gold-Proved Halos Safety Command Interceptor (`halos_safety_gate.ads` / `.adb`)

This canonical pattern implements the exact SPARK equivalent of the `/c-pro` Halos safety command interceptor—except here, **`gnatprove` mathematically proves at compile time** that:
1. No integer overflow, floating-point overflow, `NaN`/`Inf` propagation, or array bounds error can ever occur (**Silver AoRTE**).
2. Every unsafe condition (unarmed state, clock rollback, stale heartbeat $> 5\text{ ms}$, non-finite C float input, or torque limit exceedance) deterministically transitions the envelope to `State_Fault_Estop` and forces **all 6 joint output torques to `0.0`** (**Gold Functional Proof**).
3. It exports a zero-copy C23 ABI function (`halos_spark_intercept_joint_cmd`) callable directly from C23 (`/c-pro`) or C++23 (`/cpp-pro`).

### Specification (`src/halos_safety_gate.ads`)

```ada
pragma Ada_2022;
with Interfaces;   use Interfaces;
with Interfaces.C; use Interfaces.C;

package Halos_Safety_Gate
   with SPARK_Mode => On
is
   Halos_Dof_Count      : constant := 6;
   Halos_Max_Cmd_Age_Ns : constant Unsigned_64 := 5_000_000; --  5 ms watchdog

   type Dof_Index is range 0 .. Halos_Dof_Count - 1;

   --  Constrained finite torque subtype (statically excludes NaN and +/-Inf)
   Max_Hardware_Torque_Nm : constant := 500.0;
   subtype Safe_Torque_Scalar is
      C_float range -Max_Hardware_Torque_Nm .. Max_Hardware_Torque_Nm;
   subtype Non_Negative_Torque is
      C_float range 0.0 .. Max_Hardware_Torque_Nm;

   type Safe_Torque_Array is array (Dof_Index) of Safe_Torque_Scalar
      with Convention => C;

   type Torque_Limit_Array is array (Dof_Index) of Non_Negative_Torque
      with Convention => C;

   type Halos_Status is
     (Halos_Ok,
      Halos_Err_Not_Active,
      Halos_Err_Stale_Heartbeat,
      Halos_Err_Non_Finite_Input,
      Halos_Err_Torque_Limit_Exceeded)
      with Convention => C, Size => 32;

   for Halos_Status use
     (Halos_Ok                        => 0,
      Halos_Err_Not_Active            => 1,
      Halos_Err_Stale_Heartbeat       => 2,
      Halos_Err_Non_Finite_Input      => 3,
      Halos_Err_Torque_Limit_Exceeded => 4);

   pragma Warnings (Off, "the size of enums in C is implementation-defined");
   type Halos_Safety_State is
     (State_Init,
      State_Active,
      State_Fault_Estop)
      with Convention => C, Size => 8;
   pragma Warnings (On, "the size of enums in C is implementation-defined");

   for Halos_Safety_State use
     (State_Init        => 0,
      State_Active      => 1,
      State_Fault_Estop => 2);

   type Halos_Joint_Cmd is record
      Timestamp_Ns      : Unsigned_64;
      Desired_Torque_Nm : Safe_Torque_Array;
   end record
      with Convention => C;

   type Halos_Safety_Envelope is record
      Max_Abs_Torque_Nm : Torque_Limit_Array;
      State             : Halos_Safety_State;
   end record
      with Convention => C;

   --  Ghost helper predicates for readable Gold-level contracts
   function Is_Zero_Torque (T : Safe_Torque_Array) return Boolean is
     (for all I in Dof_Index => T (I) = 0.0)
      with Ghost;

   function Heartbeat_Is_Fresh
     (Cmd_Time_Ns : Unsigned_64;
      Now_Ns      : Unsigned_64) return Boolean
   is
     (Now_Ns >= Cmd_Time_Ns
      and then Now_Ns - Cmd_Time_Ns <= Halos_Max_Cmd_Age_Ns)
      with Ghost;

   function Torques_Within_Envelope
     (Desired : Safe_Torque_Array;
      Limits  : Torque_Limit_Array) return Boolean
   is
     (for all I in Dof_Index => abs (Desired (I)) <= Limits (I))
      with Ghost;

   --  Gold-proved safety command interceptor exported to C23 / C++23
   procedure Intercept_Joint_Cmd
     (Env             : in out Halos_Safety_Envelope;
      Cmd_In          :        Halos_Joint_Cmd;
      Now_Ns          :        Unsigned_64;
      Safe_Torque_Out :    out Safe_Torque_Array;
      Status          :    out Halos_Status)
      with Export        => True,
           Convention    => C,
           External_Name => "halos_spark_intercept_joint_cmd",
           Global        => null,
           Always_Terminates,
           Post          =>
             (Env.Max_Abs_Torque_Nm = Env'Old.Max_Abs_Torque_Nm)
             and then
             ((Status = Halos_Ok) =
                (Env'Old.State = State_Active
                 and then Heartbeat_Is_Fresh (Cmd_In.Timestamp_Ns, Now_Ns)
                 and then Torques_Within_Envelope
                            (Cmd_In.Desired_Torque_Nm, Env.Max_Abs_Torque_Nm)))
             and then
             (if Status = Halos_Ok then
                Env.State = State_Active
                and then Safe_Torque_Out = Cmd_In.Desired_Torque_Nm
                and then Torques_Within_Envelope
                           (Safe_Torque_Out, Env.Max_Abs_Torque_Nm)
              else
                Is_Zero_Torque (Safe_Torque_Out)
                and then (if Env'Old.State = State_Active then
                            Env.State = State_Fault_Estop
                          else
                            Env.State = Env'Old.State));

end Halos_Safety_Gate;
```

### Implementation (`src/halos_safety_gate.adb`)

```ada
pragma Ada_2022;

package body Halos_Safety_Gate
   with SPARK_Mode => On
is

   procedure Intercept_Joint_Cmd
     (Env             : in out Halos_Safety_Envelope;
      Cmd_In          :        Halos_Joint_Cmd;
      Now_Ns          :        Unsigned_64;
      Safe_Torque_Out :    out Safe_Torque_Array;
      Status          :    out Halos_Status)
   is
   begin
      Safe_Torque_Out := [others => 0.0];

      if Env.State /= State_Active then
         Status := Halos_Err_Not_Active;
         return;
      end if;

      if Now_Ns < Cmd_In.Timestamp_Ns
        or else (Now_Ns - Cmd_In.Timestamp_Ns) > Halos_Max_Cmd_Age_Ns
      then
         Env.State := State_Fault_Estop;
         Status    := Halos_Err_Stale_Heartbeat;
         return;
      end if;

      for I in Dof_Index loop
         --  'Valid checks IEEE-754 finiteness and [-500.0 .. 500.0] bounds at runtime
         pragma Warnings
           (GNATprove, Off,
            "attribute ""Valid"" is assumed to return True",
            Reason => "Defensive runtime check at C23/DMA FFI boundary");
         if not Cmd_In.Desired_Torque_Nm (I)'Valid then
            Env.State       := State_Fault_Estop;
            Safe_Torque_Out := [others => 0.0];
            Status          := Halos_Err_Non_Finite_Input;
            return;
         end if;
         pragma Warnings
           (GNATprove, On,
            "attribute ""Valid"" is assumed to return True");

         declare
            Req : constant Safe_Torque_Scalar := Cmd_In.Desired_Torque_Nm (I);
         begin
            if abs (Req) > Env.Max_Abs_Torque_Nm (I) then
               Env.State       := State_Fault_Estop;
               Safe_Torque_Out := [others => 0.0];
               Status          := Halos_Err_Torque_Limit_Exceeded;
               return;
            end if;

            Safe_Torque_Out (I) := Req;
         end;

         pragma Loop_Invariant
           (Env.State = State_Active
            and then Env.Max_Abs_Torque_Nm = Env'Loop_Entry.Max_Abs_Torque_Nm
            and then
            (for all K in Dof_Index'First .. I =>
               Safe_Torque_Out (K) = Cmd_In.Desired_Torque_Nm (K)
               and then abs (Safe_Torque_Out (K)) <= Env.Max_Abs_Torque_Nm (K)));
      end loop;

      Status := Halos_Ok;
   end Intercept_Joint_Cmd;

end Halos_Safety_Gate;
```

---

## 2. Memory-Mapped I/O (MMIO) Hardware Watchdog Register (`fsi_watchdog_mmio.ads`)

When targeting bare-metal or kernel-bypass MMIO on **ARM64** or **RISC-V RVA23 (Safety Island)**, use exact bit-level representation clauses and SPARK's four volatile properties:

```ada
pragma Ada_2022;
with Interfaces;              use Interfaces;
with System;
with System.Storage_Elements; use System.Storage_Elements;

package Fsi_Watchdog_Mmio
   with SPARK_Mode => On
is
   type UInt6  is mod 2**6  with Size => 6;
   type UInt24 is mod 2**24 with Size => 24;

   --  Hardware Status Register layout (32-bit exact bit representation)
   type Watchdog_Status_Reg is record
      Enabled       : Boolean;
      Timeout_Fault : Boolean;
      Reserved      : UInt6;
      Counter_Ticks : UInt24;
   end record
      with Size      => 32,
           Object_Size => 32,
           Bit_Order => System.Low_Order_First;

   for Watchdog_Status_Reg use record
      Enabled       at 0 range 0 .. 0;
      Timeout_Fault at 0 range 1 .. 1;
      Reserved      at 0 range 2 .. 7;
      Counter_Ticks at 0 range 8 .. 31;
   end record;

   Wdt_Base_Addr : constant Integer_Address := 16#4002_1000#;

   --  Status Register: Hardware writes asynchronously; reading clears interrupt flag
   Status_Reg : Watchdog_Status_Reg
      with Volatile,
           Async_Writers   => True,
           Async_Readers   => False,
           Effective_Reads => True,
           Effective_Writes => False,
           Import,
           Address => To_Address (Wdt_Base_Addr);
   pragma Annotate
     (GNATprove, Intentional,
      "object is unsuitable for aliasing via address clause",
      "Hardware datasheet guarantees dedicated MMIO register at 0x4002_1000");

   --  Command Pet Register: Writing magic token resets hardware watchdog timer
   Command_Reg : Unsigned_32
      with Volatile,
           Async_Writers    => False,
           Async_Readers    => True,
           Effective_Reads  => False,
           Effective_Writes => True,
           Import,
           Address => To_Address (Wdt_Base_Addr + 4);
   pragma Annotate
     (GNATprove, Intentional,
      "object is unsuitable for aliasing via address clause",
      "Hardware datasheet guarantees dedicated MMIO register at 0x4002_1004");

   Watchdog_Pet_Token : constant Unsigned_32 := 16#5AFE_F00D#;

   procedure Pet_Hardware_Watchdog (Fault_Detected : out Boolean)
      with Global => (In_Out => Status_Reg, Output => Command_Reg),
           Depends => (Fault_Detected => Status_Reg,
                       Status_Reg     => Status_Reg,
                       Command_Reg    => Status_Reg),
           Always_Terminates;

end Fsi_Watchdog_Mmio;
```

---

## 3. Jorvik Real-Time Protected Sensor Mailbox (`holoscan_sensor_mailbox.ads` / `.adb`)

For concurrent real-time tasks under `pragma Profile (Jorvik);`, use a ceiling-priority `protected` object so `gnatprove` mathematically guarantees zero data races and zero deadlocks:

```ada
pragma Ada_2022;
pragma Profile (Jorvik);
pragma Partition_Elaboration_Policy (Sequential);

with Interfaces; use Interfaces;
with System;

package Holoscan_Sensor_Mailbox
   with SPARK_Mode => On
is
   Payload_Capacity : constant := 48;
   type Payload_Index is range 0 .. Payload_Capacity - 1;
   type Payload_Bytes is array (Payload_Index) of Unsigned_8;

   subtype Valid_Payload_Len is Natural range 0 .. Payload_Capacity;

   type Sensor_Frame is record
      Timestamp_Ns : Unsigned_64       := 0;
      Sequence_Id  : Unsigned_32       := 0;
      Payload_Len  : Valid_Payload_Len := 0;
      Payload      : Payload_Bytes     := [others => 0];
   end record;

   protected type Frame_Mailbox
     (Ceiling : System.Priority := System.Priority'Last)
      with Priority => Ceiling
   is
      procedure Publish (Frame : Sensor_Frame)
         with Global => null,
              Always_Terminates;

      procedure Read_Latest
        (Frame    : out Sensor_Frame;
         Is_Valid : out Boolean)
         with Global => null,
              Always_Terminates;
   private
      Current_Frame : Sensor_Frame := (others => <>);
      Has_Data      : Boolean      := False;
   end Frame_Mailbox;

end Holoscan_Sensor_Mailbox;
```

---

## 4. Hybrid Alire + CMake 4.4.3+ Integration (Linking SPARK into C23/C++23)

When embedding a formally verified SPARK static library into a larger C23 (`/c-pro`) or C++23 (`/cpp-pro`) workspace driven by CMake 4.4.3+ (`/cmake-pro`):

1. Configure the SPARK `.gpr` file as a static Stand-Alone Library:
   ```ada
   for Library_Name use "halos_spark_safety";
   for Library_Dir use "lib";
   for Library_Kind use "static";
   for Library_Interface use ("Halos_Safety_Gate");
   for Library_Auto_Init use "True";
   for Library_Standalone use "encapsulated";
   ```
2. Register an imported static library target in `cmake/SparkTargets.cmake`:
   ```cmake
   # cmake/SparkTargets.cmake
   find_program(ALR_EXECUTABLE alr REQUIRED)

   set(SPARK_CRATE_DIR "${CMAKE_SOURCE_DIR}/spark_safety_core")
   set(SPARK_STATIC_LIB "${SPARK_CRATE_DIR}/lib/libhalos_spark_safety.a")

   add_custom_command(
       OUTPUT "${SPARK_STATIC_LIB}"
       COMMAND "${ALR_EXECUTABLE}" -n gnatprove --level=2 --warnings=error -j0
       COMMAND "${ALR_EXECUTABLE}" -n build --release
       WORKING_DIRECTORY "${SPARK_CRATE_DIR}"
       COMMENT "Formally verifying (gnatprove) and building SPARK safety library"
       VERBATIM
   )

   add_custom_target(spark_safety_build DEPENDS "${SPARK_STATIC_LIB}")

   add_library(Halos::SparkSafety STATIC IMPORTED GLOBAL)
   add_dependencies(Halos::SparkSafety spark_safety_build)
   set_target_properties(
       Halos::SparkSafety
       PROPERTIES
           IMPORTED_LOCATION "${SPARK_STATIC_LIB}"
           INTERFACE_INCLUDE_DIRECTORIES "${SPARK_CRATE_DIR}/include"
   )
   ```
