with Alr.Files;
with Alr.OS_Lib;
with Alr.Spawn;
with Alr.Utils;

package body Alr.Commands.Compile is

   -------------
   -- Execute --
   -------------

   overriding procedure Execute (Cmd : in out Command) is
      pragma Unreferenced (Cmd);
   begin
      Execute;
   end Execute;

   -------------
   -- Execute --
   -------------

   procedure Execute is
      Guard : constant Folder_Guard := Enter_Project_Folder with Unreferenced;
   begin
      Requires_Project;
      Requires_Buildfile;

      begin
         Spawn.Gprbuild (Project.GPR_Alr_File);
         if OS_Lib.File_Contains_Ignore_Case (Project.GPR_File, "Library_Name") then
            Log ("Compilation finished without errors");
         else
            declare
               Execs : constant Utils.String_Vector := Files.Locate_File_Under (".", Project.Name, 2);
               --  FIXME: extension in non-linux platforms!
            begin
               case Execs.Length is
                  when 0 =>
                     Log ("No executable found after compilation (might be too deep or have non-standard name)", Detail);
                  when others =>
                     for Exe of Execs loop
                        Trace.Info ("Executable found at " &
                               Utils.Quote (Utils.Replace ("(project)/" & Execs.First_Element,
                               "/./", "/")));
                     end loop;
               end case;
            end;
         end if;
      exception
         when Command_Failed =>
            Trace.Warning ("alr detected a compilation failure, re-run with -v or -d for details");
            raise;
      end;
   end Execute;

end Alr.Commands.Compile;
