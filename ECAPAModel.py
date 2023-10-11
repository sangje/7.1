'''
This part is used to train the speaker model and evaluate the performances
'''

import torch, sys, os, tqdm, numpy, soundfile, time, pickle
import torch.nn as nn
from tools import *
from model import ECAPA_TDNN

class ECAPAModel(nn.Module):
	def __init__(self, lr, lr_decay, C , test_step, **kwargs):
		super(ECAPAModel, self).__init__()
		## ECAPA-TDNN
		self.model = ECAPA_TDNN(C = C).cuda()
		## Classifier
		self.loss	 = nn.BCELoss()

		self.optim           = torch.optim.Adam(self.parameters(), lr = lr, weight_decay = 2e-5)
		self.scheduler       = torch.optim.lr_scheduler.StepLR(self.optim, step_size = test_step, gamma=lr_decay)
		print(time.strftime("%m-%d %H:%M:%S") + " Model para number = %.2f"%(sum(param.numel() for param in self.model.parameters()) / 1024 / 1024))

	def train_network(self, epoch, loader):
		self.train()
		## Update the learning rate based on the current epcoh
		self.scheduler.step(epoch - 1)
		loss = 0
		lr = self.optim.param_groups[0]['lr']
		for num, (data, labels) in enumerate(loader, start = 1):
			self.zero_grad()
			labels            = torch.LongTensor(labels).cuda()
			logits = self.model.forward(data.cuda(), aug = True)
			nloss = self.loss(logits, labels)			
			nloss.backward()
			self.optim.step()
			#index += len(labels)
			#top1 += prec
			loss += nloss.detach().cpu().numpy()
			sys.stderr.write(time.strftime("%m-%d %H:%M:%S") + \
			" [%2d] Lr: %5f, Training: %.2f%%, "    %(epoch, lr, 100 * (num / loader.__len__())) + \
			" Train_Loss: %.5f"        %(loss/(num)))
			sys.stderr.flush()
		return loss/num, lr

	def validate_network(self, loader):
		self.eval()
		## Update the learning rate based on the current epcoh
		loss = 0
		for num, (data, labels) in enumerate(loader, start = 1):
			labels            = torch.LongTensor(labels).cuda()
			logits = self.model.forward(data.cuda(), aug = True)
			nloss = self.loss(logits, labels)			
			loss += nloss.detach().cpu().numpy()
			sys.stderr.write(" Validate_Loss: %.5f"        %(loss/(num)))
			sys.stderr.flush()
		sys.stdout.write("\n")
		return loss/num
	
	def test_network(self, test_list, test_path):
		self.eval()
		lines = open(test_list).read().splitlines()[1:] # Header line 제외
		data_label=[]
		data_list=[]
		prediction=[]

		for index, line in enumerate(lines):
			speaker_label = int(line.split()[2]) # This is PHQ Binary {0,1}
			file_name     = os.path.join(test_path, line.split()[0]+'_AUDIO.wav') # Convert 301 > ~301_AUDIO.wav
			data_label.append(speaker_label)
			data_list.append(file_name)
		for i, data in enumerate(data_list):
			audio, sr = soundfile.read(self.data_list[i])
			prediction.append(self.model(audio).item())
		
		# Choose a threshold (e.g., 0.5) to convert probabilities to binary predictions
		threshold = 0.5
		predicted_labels = [1 if prob >= threshold else 0 for prob in prediction]

		true_labels = data_label.cpu().numpy()
		predicted_labels = predicted_labels.cpu().numpy()

		# Calculate and print the accuracy
		acc = (true_labels == predicted_labels).mean()

		# Calculate and print the F1 score
		tp = ((true_labels == 1) & (predicted_labels == 1)).sum()
		fp = ((true_labels == 0) & (predicted_labels == 1)).sum()
		fn = ((true_labels == 1) & (predicted_labels == 0)).sum()

		precision = tp / (tp + fp)
		recall = tp / (tp + fn)

		f1 = 2 * (precision * recall) / (precision + recall)
		return f1, acc

	def save_parameters(self, path):
		torch.save(self.state_dict(), path)

	def load_parameters(self, path):
		self_state = self.state_dict()
		loaded_state = torch.load(path)
		for name, param in loaded_state.items():
			origname = name
			if name not in self_state:
				name = name.replace("module.", "")
				if name not in self_state:
					print("%s is not in the model."%origname)
					continue
			if self_state[name].size() != loaded_state[origname].size():
				print("Wrong parameter length: %s, model: %s, loaded: %s"%(origname, self_state[name].size(), loaded_state[origname].size()))
				continue
			self_state[name].copy_(param)