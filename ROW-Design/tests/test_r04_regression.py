import os, unittest
from pathlib import Path
from row.data import load_excel
from row.network import build_network
from row.reduction import reduce_network
from row.config import ReductionOptions
from row.extensive_form import solve_extensive
from row.benders import solve_benders

DEFAULT=Path(r'D:\Dropbox\research papers\闫老师-夜间物流论文\test\R04_Y1.xlsx')

@unittest.skipUnless(Path(os.getenv('ROW_TEST_XLSX',DEFAULT)).exists(),'R04 workbook not available')
class TestR04Regression(unittest.TestCase):
 def test_one_binary_extensive_matches_benders(self):
  d=load_excel(Path(os.getenv('ROW_TEST_XLSX',DEFAULT))); n=build_network(d); n,_=reduce_network(d,n)
  d.candidates=[(5,2)]
  ef=solve_extensive(d,n,{1:1},gap=1e-6)
  for mode in ('BD-P','BD-NR','BD-P-NR'):
   bd=solve_benders(d,n,{1:1},mode=mode,gap=1e-6,max_iter=20)
   self.assertLessEqual(abs(ef['objective']-bd['objective']),1e-6,mode)
   self.assertLessEqual(bd['gap'],1e-6,mode)
   self.assertEqual(bd['y'][(5,2)],1.0,mode)
 def test_reduction_preserves_single_scenario_objective(self):
  p=Path(os.getenv('ROW_TEST_XLSX',DEFAULT)); off=ReductionOptions(False,False,False,False)
  d0=load_excel(p);n0=build_network(d0,off);n0,_=reduce_network(d0,n0,off);a=solve_extensive(d0,n0,{1:1},gap=1e-6)
  d1=load_excel(p);n1=build_network(d1);n1,stats=reduce_network(d1,n1);b=solve_extensive(d1,n1,{1:1},gap=1e-6)
  self.assertEqual(len(d0.candidates), len(d1.candidates))
  self.assertLessEqual(abs(a['objective']-b['objective']),1e-5)

if __name__=='__main__': unittest.main()
