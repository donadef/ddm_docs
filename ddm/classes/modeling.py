# -*- coding: utf-8 -*-
import os
import shutil
import subprocess

from tools import cgenff_charmm2gmx
from .base import DDMClass, clean_md_files, clean_tmp


class Modeling(DDMClass):
    def __init__(self, config, complex, guest):
        super(Modeling, self).__init__(config, complex)
        self.directory = os.path.join(self.dest, '00-modeling')
        self.static_dir = os.path.join(self.static_dir, '00-modeling')
        self.guest = guest

    def run(self):
        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

        # Copy the complex pdb in the folder
        shutil.copy(self.complex, self.directory)

        os.chdir(self.directory)

        # Guest
        self.prepare_guest()
        self.minimize_guest()

        # Host
        self.prepare_host()

        # Complex
        self.minimize_complex()

        self.files_to_store = [self.guest.name + '.top', self.guest.name + '.prm', self.guest.name + '.itp', self.guest.name + '_ini.pdb', 'topol-ligand.top', 'ligand_mini.pdb',
                               self.host + '.top', self.host + '.prm', self.host + '.itp', self.host + '_ini.pdb',
                               'complex_mini.pdb', 'topol-complex.top']
        self.store_files()

    def prepare_guest(self):
        # PDB param file for the guest
        if not os.path.isfile(os.path.join(self.directory, self.guest.name + '.top')):
            self.generate_param_files(self.guest.name, self.guest.pdb_file_path)

    def minimize_guest(self):
        if not os.path.isfile(os.path.join(self.directory, 'ligand_mini.pdb')):
            if not os.path.isfile(os.path.join(self.directory, 'topol-ligand.top')):
                # create the topol-ligand.top file
                f = open(os.path.join(self.static_dir, 'ligand.top'), 'r')
                filedata = f.read()
                f.close()

                newdata = filedata.replace("XXXXX", self.guest.name)

                f = open(os.path.join(self.directory, 'topol-ligand.top'), 'w')
                f.write(newdata)
                f.close()

            # First minimization step, steepest descent method.
            if not os.path.isfile(os.path.join(self.directory, 'mini1.trr')):
                self.minimize1(self.guest.name + '_ini', 'topol-ligand')

            # Second minimization step, conjugate gradient method.
            if not os.path.isfile(os.path.join(self.directory, 'mini2.trr')):
                self.minimize2('topol-ligand')

            # Extract coordinates
            if not os.path.isfile(os.path.join(self.directory, 'TMP')):
                self.minimize2('topol-ligand')
            self.extract_coordinates('ligand_mini')

            clean_md_files()
            clean_tmp()

    def prepare_host(self):
        # PDB file for the host, extract from the complex given as input.
        if not os.path.isfile(os.path.join(self.directory, self.host + '.pdb')):
            subprocess.call('grep " ' + self.host + ' " ' + self.ipdb + '.pdb' + ' > ' + os.path.join(self.directory, self.host + '.pdb'),
                            shell=True)
        if not os.path.isfile(os.path.join(self.directory, self.host + '.top')):
            self.generate_param_files(self.host)

    def minimize_complex(self):
        if not os.path.isfile(os.path.join(self.directory, 'complex_mini.pdb')):
            if not os.path.isfile(os.path.join(self.directory, 'topol-complex.top')):
                # create the topol-complex.top file
                f = open(os.path.join(self.static_dir, 'complex.top'), 'r')
                filedata = f.read()
                f.close()

                newdata = filedata.replace('XXXXX', self.host)
                newdata = newdata.replace('YYYYY', self.guest.name)

                f = open(os.path.join(self.directory, 'topol-complex.top'), 'w')
                f.write(newdata)
                f.close()

            # First minimization step, steepest descent method.
            if not os.path.isfile(os.path.join(self.directory, 'mini1.trr')):
                self.minimize1(self.ipdb, 'topol-complex')

            # Second minimization step, conjugate gradient method.
            if not os.path.isfile(os.path.join(self.directory, 'mini2.trr')):
                self.minimize2('topol-complex')

            # Extract coordinates
            if not os.path.isfile(os.path.join(self.directory, 'TMP')):
                self.minimize2('topol-complex')
            self.extract_coordinates('complex_mini')

            clean_md_files()
            clean_tmp()

    def generate_param_files(self, who, pdb):
        subprocess.call('babel -ipdb ' + pdb + ' -omol2 ' + who + '.mol2 --title ' + who,
                        shell=True)

        subprocess.call('cgenff ' + who + '.mol2 > ' + who + '.str',
                        shell=True)

        # Use cgenff_charmm2gmx (in the project) to create param for gmx
        mol_name = who
        mol2_name = who + '.mol2'
        rtp_name = who + '.str'
        GMXDATA = os.environ['GMXDATA']
        ffdir = os.path.join(GMXDATA, 'top/charmm36-jul2017.ff')
        cgenff_charmm2gmx.main(mol_name, mol2_name, rtp_name, ffdir)

        # Correct file names
        os.rename(who.lower() + '.top', who + '.top')
        os.rename(who.lower() + '.prm', who + '.prm')
        os.rename(who.lower() + '.itp', who + '.itp')
        os.rename(who.lower() + '_ini.pdb', who + '_ini.pdb')

    def minimize1(self, pdb, top):
        subprocess.call('gmx grompp -f ' + os.path.join(self.static_dir, 'MINI1.mdp') + ' -c ' + pdb + '.pdb -p ' + top + '.top -o mini1.tpr -maxwarn 2',
                        shell=True)
        subprocess.call('gmx_d mdrun -v -deffnm mini1',
                        shell=True)

    def minimize2(self, top):
        subprocess.call('gmx grompp -f ' + os.path.join(self.static_dir, 'MINI2.mdp') + ' -c mini1.gro -p ' + top + '.top -o mini2.tpr -maxwarn 2',
                        shell=True)
        subprocess.call('gmx_d mdrun -v -deffnm mini2 > TMP 2>&1',
                        shell=True)

    def extract_coordinates(self, pdb):
        # Find the number of the last step
        nstep = subprocess.check_output("grep 'Step' TMP | tail -1 | awk '{print $2}' | sed s/','//g",
                                        shell=True).decode("utf-8").rstrip('\n')
        # Extract the coordinate for the last step
        subprocess.call('echo "0" | gmx trjconv -f mini2.trr -s mini2.tpr -o ' + pdb + '.pdb -b ' + nstep,
                        shell=True)